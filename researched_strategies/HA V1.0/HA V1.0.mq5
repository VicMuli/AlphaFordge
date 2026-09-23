//+------------------------------------------------------------------+
//|                                    HA_Oxfordstrat_XAUUSD.mq5      |
//|  Heikin-Ashi Technique (Setup & Exit) - Oxfordstrat R&D Blog      |
//|  https://oxfordstrat.com/trading-strategies/heikin-ashi-1/        |
//|                                                                    |
//|  Logic:                                                           |
//|   1. AvgOHLC[i] = SMA(OHLC, Look_Back)                            |
//|   2. Recursive Heikin-Ashi built on the averaged OHLC              |
//|   3. Setup:  HaClose[i-1] > HaOpen[i-1] -> bullish                 |
//|              HaClose[i-1] < HaOpen[i-1] -> bearish                 |
//|   4. Entry:  market order at the open of the current bar           |
//|   5. Exit:   (a) Time exit after Time_Index bars                   |
//|              (b) ATR(20) x ATR_Stop protective stop                |
//|                                                                     |
//|  Timeframe adapted to M5 (original research used daily bars).      |
//+------------------------------------------------------------------+
#property copyright "Adapted for AlphaForge / MT5 backtesting"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//--- Strategy inputs (optimizable per user request)
input group "=== Timeframe ==="
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M5;  // Working timeframe (M1, M5, M15, M30, H1, H4, D1, ...)

input group "=== Heikin-Ashi Setup ==="
input int      InpLookBack        = 20;    // Look_Back: SMA period applied to OHLC before HA calc (optimize 1-141 step 5)
input int      InpTimeIndex       = 20;    // Time_Index: bars held before forced time exit (optimize 1-141 step 5)

input group "=== Body-Size Filter (oxfordstrat heikin-ashi-2 spec) ==="
input bool     InpUseBodyFilter   = true;  // Enable Body_Index wick filter (toggle for isolated testing)
input double   InpBodyIndex       = 0.10;  // Body_Index: max opposite-wick fraction of range (optimize 0.00-0.30 step 0.01)

input group "=== Trend Filter (oxfordstrat heikin-ashi-2 spec) ==="
input bool     InpUseTrendFilter  = true;  // Enable Trend_Index momentum filter (toggle for isolated testing)
input int      InpTrendIndex      = 20;    // Trend_Index: lookback bars for Close momentum check (optimize 1-141 step 5)

input group "=== Protective Stop (fixed per original spec) ==="
input int      InpATRLength       = 20;    // ATR_Length
input double   InpATRStop         = 6.0;   // ATR_Stop multiplier

input group "=== Position Sizing ==="
input double   InpLotSize         = 0.10;  // Fixed lot size per trade

input group "=== Execution ==="
input int      InpHistoryDepth    = 500;   // Bars of history used to stabilize the recursive HA calc
input int      InpSlippage        = 20;    // Max slippage, points
input long     InpMagic           = 20260922; // Magic number

//--- Globals
CTrade   trade;
datetime g_lastBarTime   = 0;
datetime g_entryBarTime  = 0;
int      g_atrHandle     = INVALID_HANDLE;

//+------------------------------------------------------------------+
int OnInit()
{
   if(InpLookBack < 1 || InpTimeIndex < 1)
   {
      Print("InpLookBack and InpTimeIndex must be >= 1");
      return(INIT_PARAMETERS_INCORRECT);
   }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFillingBySymbol(_Symbol);

   g_atrHandle = iATR(_Symbol, InpTimeframe, InpATRLength);
   if(g_atrHandle == INVALID_HANDLE)
   {
      Print("Failed to create ATR handle");
      return(INIT_FAILED);
   }

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_atrHandle != INVALID_HANDLE)
      IndicatorRelease(g_atrHandle);
}

//+------------------------------------------------------------------+
//| Recompute the averaged-OHLC Heikin-Ashi series and return the     |
//| HaOpen/HaClose of the LAST COMPLETED bar (shift = 1).             |
//| Full recompute each call keeps the recursive HA series stable     |
//| (avoids drift from persisting state across ticks/optimizer runs). |
//+------------------------------------------------------------------+
bool CalculateHeikinAshi(int lookBack, int historyDepth, double &haOpenOut, double &haCloseOut, double &haHighOut, double &haLowOut)
{
   int total = historyDepth + lookBack + 5;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(_Symbol, InpTimeframe, 1, total, rates); // shift 1 = last CLOSED bar onward into history
   if(copied < lookBack + 2)
      return false;

   ArraySetAsSeries(rates, false); // reorder oldest -> newest for forward recursion
   int n = copied;

   double avgOpen[], avgHigh[], avgLow[], avgClose[];
   ArrayResize(avgOpen, n);
   ArrayResize(avgHigh, n);
   ArrayResize(avgLow,  n);
   ArrayResize(avgClose,n);

   for(int i = lookBack - 1; i < n; i++)
   {
      double sO=0.0, sH=0.0, sL=0.0, sC=0.0;
      for(int k = 0; k < lookBack; k++)
      {
         sO += rates[i-k].open;
         sH += rates[i-k].high;
         sL += rates[i-k].low;
         sC += rates[i-k].close;
      }
      avgOpen[i]  = sO / lookBack;
      avgHigh[i]  = sH / lookBack;
      avgLow[i]   = sL / lookBack;
      avgClose[i] = sC / lookBack;
   }

   double haOpen[], haClose[], haHigh[], haLow[];
   ArrayResize(haOpen, n);
   ArrayResize(haClose,n);
   ArrayResize(haHigh, n);
   ArrayResize(haLow,  n);

   int start = lookBack - 1;
   haClose[start] = (avgOpen[start] + avgHigh[start] + avgLow[start] + avgClose[start]) / 4.0;
   haOpen[start]  = (avgOpen[start] + avgClose[start]) / 2.0;
   haHigh[start]  = avgHigh[start];
   haLow[start]   = avgLow[start];

   for(int i = start + 1; i < n; i++)
   {
      haClose[i] = (avgOpen[i] + avgHigh[i] + avgLow[i] + avgClose[i]) / 4.0;
      haOpen[i]  = (haOpen[i-1] + haClose[i-1]) / 2.0;
      haHigh[i]  = MathMax(avgHigh[i], MathMax(haOpen[i], haClose[i]));
      haLow[i]   = MathMin(avgLow[i],  MathMin(haOpen[i],  haClose[i]));
   }

   haOpenOut  = haOpen[n-1];
   haCloseOut = haClose[n-1];
   haHighOut  = haHigh[n-1];
   haLowOut   = haLow[n-1];
   return true;
}

//+------------------------------------------------------------------+
//| Body-size (wick) filter, oxfordstrat heikin-ashi-2 spec:          |
//|  Long:  (HaOpen - HaLow)  <= (HaHigh - HaLow) * BodyIndex          |
//|  Short: (HaHigh - HaOpen) <= (HaHigh - HaLow) * BodyIndex          |
//| Requires the trailing wick opposite the trend to be small,        |
//| i.e. a "clean" trend bar rather than an indecisive/choppy one.    |
//+------------------------------------------------------------------+
bool PassesBodyFilter(int signal, double haOpen, double haHigh, double haLow, double bodyIndex)
{
   double range = haHigh - haLow;
   if(range <= 0.0)
      return false; // degenerate bar, treat as filtered out

   if(signal == 1)
      return ((haOpen - haLow) <= (range * bodyIndex));
   else if(signal == -1)
      return ((haHigh - haOpen) <= (range * bodyIndex));

   return false;
}

//+------------------------------------------------------------------+
//| Trend momentum filter, oxfordstrat heikin-ashi-2 spec:            |
//|  Long:  Close[i-1] > Close[i-1-Trend_Index]                       |
//|  Short: Close[i-1] < Close[i-1-Trend_Index]                       |
//| Requires raw price to have net-moved in the setup's direction     |
//| over the Trend_Index lookback, i.e. only take HA reversals that   |
//| agree with the prevailing higher-level trend.                     |
//+------------------------------------------------------------------+
bool PassesTrendFilter(int signal, int trendIndex)
{
   double closeNear = iClose(_Symbol, InpTimeframe, 1);
   double closeFar   = iClose(_Symbol, InpTimeframe, 1 + trendIndex);
   if(closeNear == 0.0 || closeFar == 0.0)
      return false; // not enough history

   if(signal == 1)
      return (closeNear > closeFar);
   else if(signal == -1)
      return (closeNear < closeFar);

   return false;
}

//+------------------------------------------------------------------+
bool IsNewBar()
{
   datetime t = iTime(_Symbol, InpTimeframe, 0);
   if(t != g_lastBarTime)
   {
      g_lastBarTime = t;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
double GetATR()
{
   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(g_atrHandle, 0, 1, 1, buf) < 1)
      return 0.0;
   return buf[0];
}

//+------------------------------------------------------------------+
int BarsHeldSinceEntry(datetime currentBarTime)
{
   if(g_entryBarTime == 0) return 0;
   long secs = (long)(currentBarTime - g_entryBarTime);
   int periodSecs = PeriodSeconds(InpTimeframe);
   if(periodSecs <= 0) return 0;
   return (int)(secs / periodSecs);
}

//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   return PositionSelect(_Symbol);
}

//+------------------------------------------------------------------+
void ClosePosition()
{
   if(PositionSelect(_Symbol))
      trade.PositionClose(_Symbol);
}

//+------------------------------------------------------------------+
void OpenLong(double atrValue)
{
   double price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double sl    = price - atrValue * InpATRStop;
   trade.Buy(InpLotSize, _Symbol, price, sl, 0.0, "HA_Oxfordstrat");
}

//+------------------------------------------------------------------+
void OpenShort(double atrValue)
{
   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl    = price + atrValue * InpATRStop;
   trade.Sell(InpLotSize, _Symbol, price, sl, 0.0, "HA_Oxfordstrat");
}

//+------------------------------------------------------------------+
void OnTick()
{
   if(!IsNewBar())
      return;

   datetime currentBarTime = iTime(_Symbol, InpTimeframe, 0);

   //--- 1. Time-based exit check on any open position
   if(HasOpenPosition())
   {
      int barsHeld = BarsHeldSinceEntry(currentBarTime);
      if(barsHeld >= InpTimeIndex)
      {
         ClosePosition();
         g_entryBarTime = 0;
      }
   }

   //--- 2. Recompute Heikin-Ashi setup on the last CLOSED bar
   double haOpen, haClose, haHigh, haLow;
   if(!CalculateHeikinAshi(InpLookBack, InpHistoryDepth, haOpen, haClose, haHigh, haLow))
      return; // not enough history yet

   int signal = 0; // 1 = bullish, -1 = bearish, 0 = flat/none
   if(haClose > haOpen) signal = 1;
   else if(haClose < haOpen) signal = -1;

   if(signal == 0)
      return;

   //--- 2b. Body-size filter: reject choppy/indecisive setups
   if(InpUseBodyFilter && !PassesBodyFilter(signal, haOpen, haHigh, haLow, InpBodyIndex))
      return;

   //--- 2c. Trend momentum filter: only take HA reversals aligned with the broader trend
   if(InpUseTrendFilter && !PassesTrendFilter(signal, InpTrendIndex))
      return;

   double atrValue = GetATR();
   if(atrValue <= 0.0)
      return;

   //--- 3. Manage / enter positions based on signal
   if(HasOpenPosition())
   {
      long posType = PositionGetInteger(POSITION_TYPE);
      bool isLong  = (posType == POSITION_TYPE_BUY);
      bool isShort = (posType == POSITION_TYPE_SELL);

      if(signal == 1 && isShort)
      {
         ClosePosition();
         OpenLong(atrValue);
         g_entryBarTime = currentBarTime;
      }
      else if(signal == -1 && isLong)
      {
         ClosePosition();
         OpenShort(atrValue);
         g_entryBarTime = currentBarTime;
      }
      // else: signal agrees with current position direction -> hold, let time/ATR exit manage it
   }
   else
   {
      if(signal == 1)
      {
         OpenLong(atrValue);
         g_entryBarTime = currentBarTime;
      }
      else if(signal == -1)
      {
         OpenShort(atrValue);
         g_entryBarTime = currentBarTime;
      }
   }
}
//+------------------------------------------------------------------+