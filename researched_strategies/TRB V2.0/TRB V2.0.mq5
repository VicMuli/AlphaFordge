//+------------------------------------------------------------------+
//|                                                  TRB V2.0.mq5   |
//|                                  Copyright 2026, Victor Muli |
//+------------------------------------------------------------------+
//  CHANGELOG V2.0
//  + Per-Instance Log Tagging - every "TRB:" log line, the OnInit
//    summary, and the pending-order comment now include [Magic=...],
//    so running several instances of this EA on separate charts of the
//    same symbol (e.g. 8 USDJPY charts with different ADX/ATR settings)
//    produces a log you can filter/grep per instance in the shared
//    Experts tab. The ADX/ATR block-log lines also now print the
//    actual computed ADX/ATR reading alongside the threshold, not just
//    the threshold, so you can directly confirm each chart's filter is
//    evaluating differently.
//  - REMOVED News Filter entirely (UseNewsFilter, NewsBlockMinutesBefore/
//    After, the hardcoded newsSchedule[] table, and IsNewsWindow()).
//    Session-blocking logic now only checks the Monthly DD circuit
//    breaker before placing orders.
//  - REMOVED ATR Trailing Stop entirely (UseAtrTrailingStop,
//    AtrTrailPeriod, AtrTrailMultiplier, AtrTrailTimeframe,
//    ManageAtrTrailingStop(), the atrTrailHandle indicator handle, and
//    its per-bar trailLastBarTime gate). Open positions are no longer
//    trailed -- SL/TP set at entry stand until the hard close at
//    CloseHourGMT (or the daily/monthly circuit breakers).
//  + Chart Indicator Display - EMA/ADX/ATR handles (whichever filters
//    are enabled) are now attached directly to the chart via
//    ChartIndicatorAdd() in OnInit, so they're visible during both
//    Strategy Tester (visual mode) and live/demo trading. They render
//    at whatever timeframe their own input (EMATimeframe/AdxTimeframe/
//    AtrTimeframe) is set to -- all default to M15, so out of the box
//    you see the 200 EMA on the main chart plus ADX and ATR in their
//    own subwindows, all computed off the M15 series, regardless of
//    what period the chart itself is opened on. New input:
//    ShowIndicatorsOnChart (default true).
//  + Session Range Visualization - DrawSessionRange() draws a rectangle
//    spanning the Tokyo session high/low from session start out to the
//    hard-close hour, plus a small text label with the range size in
//    pips, every time a session is evaluated (whether or not a trade is
//    ultimately taken). Objects are time/price-anchored so they display
//    correctly on any chart period, including M15. New input:
//    ShowSessionRangeOnChart (default true).
//
//  CHANGELOG V1.9
//  + ADX Trend Strength Filter - session-level gate, blocks trading a
//    session entirely if trend strength is below AdxMin. Screens out
//    choppy/ranging Tokyo sessions, the usual source of false breakouts.
//  + ATR Volatility Floor Filter - session-level gate, blocks trading a
//    session if recent volatility is below AtrMinPips. Screens out dead,
//    low-movement sessions unlikely to reach the TP distance.
//  + ATR Trailing Stop - once a position is open, tightens its SL toward
//    current price by ATR*AtrTrailMultiplier once per new M1 bar, never
//    loosening it. Does not change initial entry risk -- only affects
//    how much open profit gets given back on a reversal.
//  All three default OFF (UseAdxFilter/UseAtrFilter/UseAtrTrailingStop),
//  so existing behavior is unchanged until explicitly enabled.
//  NOTE: risk-based sizing (V1.8) alone did not fully resolve the high
//  Monte Carlo daily-drawdown-breach rate seen in backtesting -- these
//  filters are aimed at a different angle on that same problem: avoiding
//  low-conviction/choppy sessions in the first place, rather than only
//  controlling how large a loss costs once a trade is taken.
//
//  CHANGELOG V1.8
//  + Risk-based position sizing - LotSize was previously applied flat
//    regardless of that session's actual stop distance (which varies
//    with the range width + 2*PipsOffset). Backtest data showed
//    individual trades losing up to ~4.7% of equity in a single stop-out
//    at a fixed lot -- meaning the daily-loss circuit breaker (nominally
//    a 4% cap) could still be blown through in ONE fill, since it can
//    only react to equity after a loss lands, not prevent an already-
//    oversized stop-loss order from executing. GetLotSize() now sizes
//    each order off that session's REAL stop distance so a full stop-out
//    always costs a consistent RiskPercent of equity. Default ON
//    (UseRiskBasedSizing); LotSize remains as a fallback/manual override.
//
//  CHANGELOG V1.7
//  + Daily Loss Limit - hard stop for prop firm compliance (FTMO 5% rule)
//  Base: TRB V1.5 Fixed (Tickstory UTC fix, monthly DD, EMA filter, range filter)
//+------------------------------------------------------------------+
#property version   "2.00"
#property description "Tokyo Range Breakout - Prop Firm Ready | ADX/ATR Filters + Risk Sizing + Chart Visuals"
#property copyright "AI Collaborator"
#property strict

#include <Trade\Trade.mqh>

//--- Global Objects
CTrade trade;

//==========================================================================
//  INPUT PARAMETERS
//==========================================================================

//--- Core Settings
input ulong  MagicNumber             = 881024;   // Magic Number
input double LotSize                 = 0.1;      // Lot Size (fallback/manual-override -- see UseRiskBasedSizing below)

//--- Risk Management
input bool   UseRiskBasedSizing      = true;     // Size by % equity risk instead of a flat lot (recommended)
input double RiskPercent             = 1.0;      // % of equity risked per trade (only used if UseRiskBasedSizing)
//  WHY THIS EXISTS: LotSize used to be applied flat regardless of that
//  session's actual stop distance (rangeWidth + 2*PipsOffset, which varies
//  session to session within [MinRangePips, MaxRangePips]). At a fixed lot,
//  a wide-range day and a tight-range day risked very different % of
//  equity for the SAME lot size -- concretely, backtest data showed
//  individual trades losing up to ~4.7% of account balance in a single
//  stop-out at LotSize=0.2, which is why the daily-loss circuit breaker
//  below (nominally a 4% cap) could still be blown through in one fill:
//  the breaker only reacts to equity AFTER a loss lands, it can't stop an
//  already-oversized stop-loss order from executing. The old "use 3.0 for
//  prop firm 10% DD limit" guidance did not account for this and is not
//  a safe recommendation -- with risk-based sizing on, LotSize below is
//  only a fallback (used if UseRiskBasedSizing is false, or if the broker
//  doesn't report tick value/size).

//--- Strategy Parameters
input int    PipsOffset              = 7;         // Range Buffer (Pips)
input double TPMultiplier            = 2.0;       // Take Profit Multiplier
input int    MinRangePips            = 35;        // Minimum Range Size to Trade (Pips)
input int    MaxRangePips            = 100;       // Maximum Range Size - 0 = disabled

//--- Session Configuration (GMT/UTC)
input int    StartHourGMT            = 0;         // Tokyo Session Start Hour (GMT)
input int    EndHourGMT              = 6;         // Tokyo Session End & Order Time (GMT)
input int    CancelHourGMT           = 9;         // Cancel Unfilled Orders Hour (GMT)
input int    CloseHourGMT            = 12;        // Hard Position Close Hour (GMT)

//--- EMA Trend Filter
input bool   UseTrendFilter          = true;      // Enable M15 200 EMA Trend Filter
input int    EMAPeriod               = 200;       // EMA Period
input ENUM_TIMEFRAMES EMATimeframe   = PERIOD_M15;// EMA Timeframe

//--- ADX Trend Strength Filter
input bool   UseAdxFilter            = false;     // Enable ADX filter (screens out choppy/ranging sessions)
input int    AdxPeriod               = 14;
input double AdxMin                  = 20.0;      // Min ADX required to trade this session
input ENUM_TIMEFRAMES AdxTimeframe   = PERIOD_M15;

//--- ATR Volatility Floor Filter
input bool   UseAtrFilter            = false;     // Enable ATR filter (screens out dead/low-movement sessions)
input int    AtrPeriod               = 14;
input double AtrMinPips              = 0.0;       // Min ATR (in pips) required to trade this session
input ENUM_TIMEFRAMES AtrTimeframe   = PERIOD_M15;

//--- Chart Visuals (NEW in V2.0)
input bool   ShowIndicatorsOnChart   = true;      // Attach enabled EMA/ADX/ATR indicators to the chart
input bool   ShowSessionRangeOnChart = true;      // Draw a box + label for each Tokyo session range

//--- Monthly Drawdown Circuit Breaker
input bool   UseMonthlyDDLimit       = true;      // Enable Monthly DD Circuit Breaker
input double MonthlyDDPercent        = 3.0;       // Monthly DD % Limit Before Pause

//--- Daily Loss Limit (Prop Firm Compliance)
input bool   UseDailyLossLimit       = true;      // Enable Daily Loss Limit
input double DailyLossPercent        = 4.0;       // Max Daily Loss % (set below firm's 5% rule)
//  HOW IT WORKS:
//  Snapshots account equity at the start of each trading day (00:00 GMT).
//  If intraday drawdown from that snapshot reaches DailyLossPercent:
//    1. All open positions are closed immediately
//    2. All pending orders are cancelled
//    3. No new orders are placed for the rest of that day
//  FTMO rule is 5% daily - default 4% gives a 1% safety buffer

//--- Time Synchronisation
input int    BacktestOffset          = 0;         // GMT Offset (0 = Tickstory UTC data)
//  Set 0 for Tickstory UTC+0 backtesting
//  Set 2 for IC Markets broker server (winter)
//  Set 3 for IC Markets broker server (summer/DST)

//==========================================================================
//  GLOBAL STATE
//==========================================================================

//--- Day tracking flags
static int    orderDay               = -1;
static int    cancelDay              = -1;
static int    closeDay               = -1;

//--- Monthly DD state
static int    monthlyResetMonth      = -1;
static double monthlyStartBalance    = 0;

//--- Daily loss limit state
static int    dailyResetDay          = -1;
static double dailyStartEquity       = 0;
static bool   dailyLimitBreached     = false;

//--- Indicator handles
int emaHandle     = INVALID_HANDLE;
int adxHandle     = INVALID_HANDLE;
int atrHandle     = INVALID_HANDLE;

//==========================================================================
//  OnInit
//==========================================================================
int OnInit()
{
   trade.SetExpertMagicNumber(MagicNumber);

   if(UseTrendFilter)
   {
      emaHandle = iMA(Symbol(), EMATimeframe, EMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
      if(emaHandle == INVALID_HANDLE)
         PrintFormat("TRB V2.0 [Magic=%d] WARNING: EMA handle failed - trend filter bypassed", (int)MagicNumber);
   }

   if(UseAdxFilter)
   {
      adxHandle = iADX(Symbol(), AdxTimeframe, AdxPeriod);
      if(adxHandle == INVALID_HANDLE)
         PrintFormat("TRB V2.0 [Magic=%d] WARNING: ADX handle failed - ADX filter bypassed", (int)MagicNumber);
   }

   if(UseAtrFilter)
   {
      atrHandle = iATR(Symbol(), AtrTimeframe, AtrPeriod);
      if(atrHandle == INVALID_HANDLE)
         PrintFormat("TRB V2.0 [Magic=%d] WARNING: ATR handle failed - ATR filter bypassed", (int)MagicNumber);
   }

   if(ShowIndicatorsOnChart)
      AttachIndicatorsToChart();

   if(UseRiskBasedSizing)
      PrintFormat("TRB V2.0 [Magic=%d] INIT | Symbol=%s | Sizing=Risk-based (%.2f%% equity/trade) | Offset=%d | DailyLimit=%.1f%% | ADX=%s(min %.1f) | ATR=%s(min %.1f pips)",
                  (int)MagicNumber, Symbol(), RiskPercent, BacktestOffset, DailyLossPercent,
                  UseAdxFilter ? "ON" : "OFF", AdxMin,
                  UseAtrFilter ? "ON" : "OFF", AtrMinPips);
   else
      PrintFormat("TRB V2.0 [Magic=%d] INIT | Symbol=%s | Sizing=Flat lot=%.2f | Offset=%d | DailyLimit=%.1f%% | ADX=%s(min %.1f) | ATR=%s(min %.1f pips)",
                  (int)MagicNumber, Symbol(), LotSize, BacktestOffset, DailyLossPercent,
                  UseAdxFilter ? "ON" : "OFF", AdxMin,
                  UseAtrFilter ? "ON" : "OFF", AtrMinPips);
   return(INIT_SUCCEEDED);
}

//==========================================================================
//  OnDeinit
//==========================================================================
void OnDeinit(const int reason)
{
   if(emaHandle      != INVALID_HANDLE) IndicatorRelease(emaHandle);
   if(adxHandle      != INVALID_HANDLE) IndicatorRelease(adxHandle);
   if(atrHandle      != INVALID_HANDLE) IndicatorRelease(atrHandle);
}

//==========================================================================
//  AttachIndicatorsToChart (NEW in V2.0) - attaches whichever indicator
//  handles are currently in use to the chart, so they're visible in both
//  the Strategy Tester (visual mode) and live/demo trading. EMA overlays
//  the main window; ADX/ATR each get their own subwindow since they're
//  oscillators. They render at whatever timeframe their own input
//  specifies (EMATimeframe/AdxTimeframe/AtrTimeframe) -- all default to
//  PERIOD_M15. Safe to call even
//  when no chart exists (e.g. non-visual backtest): ChartIndicatorAdd
//  simply fails silently in that case.
//==========================================================================
void AttachIndicatorsToChart()
{
   long chartId = ChartID();

   if(UseTrendFilter && emaHandle != INVALID_HANDLE)
      ChartIndicatorAdd(chartId, 0, emaHandle);   // main window overlay

   if(UseAdxFilter && adxHandle != INVALID_HANDLE)
   {
      int sub = (int)ChartGetInteger(chartId, CHART_WINDOWS_TOTAL);
      ChartIndicatorAdd(chartId, sub, adxHandle);
   }

   if(UseAtrFilter && atrHandle != INVALID_HANDLE)
   {
      int sub = (int)ChartGetInteger(chartId, CHART_WINDOWS_TOTAL);
      ChartIndicatorAdd(chartId, sub, atrHandle);
   }
}

//==========================================================================
//  OnTick
//==========================================================================
void OnTick()
{
   //--- Convert current time to GMT
   datetime gmtTime = TimeCurrent() - BacktestOffset * 3600;
   MqlDateTime dt;
   TimeToStruct(gmtTime, dt);

   //------------------------------------------------------------------
   //  DAILY LOSS LIMIT - reset snapshot at start of each GMT day
   //------------------------------------------------------------------
   if(UseDailyLossLimit)
   {
      if(dt.day != dailyResetDay)
      {
         dailyStartEquity    = AccountInfoDouble(ACCOUNT_EQUITY);
         dailyResetDay       = dt.day;
         dailyLimitBreached  = false;
         PrintFormat("TRB [Magic=%d]: Daily reset - equity snapshot = %.2f", (int)MagicNumber, dailyStartEquity);
      }

      //--- Check daily loss every tick if not already breached
      if(!dailyLimitBreached && dailyStartEquity > 0)
      {
         double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
         double dailyDD       = ((dailyStartEquity - currentEquity) / dailyStartEquity) * 100.0;

         if(dailyDD >= DailyLossPercent)
         {
            dailyLimitBreached = true;
            PrintFormat("TRB [Magic=%d]: DAILY LIMIT BREACHED - DD=%.2f%% >= %.2f%% | Closing all & halting today",
                        (int)MagicNumber, dailyDD, DailyLossPercent);
            CloseAllActivePositions();
            CancelPendingOrders();
         }
      }

      //--- If daily limit is breached do nothing else today
      if(dailyLimitBreached) return;
   }

   //------------------------------------------------------------------
   //  MONTHLY DD CIRCUIT BREAKER - reset on new month
   //------------------------------------------------------------------
   if(UseMonthlyDDLimit && dt.mon != monthlyResetMonth)
   {
      monthlyStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
      monthlyResetMonth   = dt.mon;
      PrintFormat("TRB [Magic=%d]: Monthly reset - balance snapshot = %.2f", (int)MagicNumber, monthlyStartBalance);
   }

   //--- OCO: cancel pending if active position exists
   if(HasActivePosition())
      CancelPendingOrders();

   //------------------------------------------------------------------
   //  STEP 1+2: Place orders at Tokyo session end (EndHourGMT GMT)
   //------------------------------------------------------------------
   if(dt.hour == EndHourGMT && dt.min == 0 && orderDay != dt.day)
   {
      orderDay = dt.day;

      if(!HasActivePosition())
      {
         //--- Monthly DD check
         bool blocked = false;

         if(UseMonthlyDDLimit && monthlyStartBalance > 0)
         {
            double monthlyDD = ((monthlyStartBalance - AccountInfoDouble(ACCOUNT_BALANCE))
                               / monthlyStartBalance) * 100.0;
            if(monthlyDD >= MonthlyDDPercent)
            {
               PrintFormat("TRB [Magic=%d]: Monthly circuit breaker ACTIVE - DD=%.2f%% >= %.2f%%",
                           (int)MagicNumber, monthlyDD, MonthlyDDPercent);
               blocked = true;
            }
         }

         if(!blocked)
            PlaceTokyoOrders(gmtTime);
      }
   }

   //------------------------------------------------------------------
   //  STEP 3: Cancel unfilled orders at CancelHourGMT
   //------------------------------------------------------------------
   if(dt.hour == CancelHourGMT && dt.min == 0 && cancelDay != dt.day)
   {
      cancelDay = dt.day;
      CancelPendingOrders();
   }

   //------------------------------------------------------------------
   //  STEP 4: Hard close at CloseHourGMT
   //------------------------------------------------------------------
   if(dt.hour == CloseHourGMT && dt.min == 0 && closeDay != dt.day)
   {
      closeDay = dt.day;
      CloseAllActivePositions();
   }
}

//==========================================================================
//  CheckAdxFilter - session-level gate. Requires sufficient trend
//  strength before trusting today's range breakout at all -- screens out
//  choppy/ranging sessions, which is normally the biggest source of false
//  breakouts in a range-breakout system. Fails CLOSED (blocks trading) if
//  the indicator data isn't ready, same convention as the DD checks.
//  outVal receives the actual ADX reading (0 if unavailable) so the
//  caller can log which chart/instance saw what value.
//==========================================================================
bool CheckAdxFilter(double &outVal)
{
   outVal = 0.0;
   if(!UseAdxFilter) return true;
   if(adxHandle == INVALID_HANDLE) return true;   // filter enabled but handle never created -- don't block
   double val[];
   if(CopyBuffer(adxHandle, 0, 1, 1, val) <= 0) return false;
   outVal = val[0];
   return val[0] >= AdxMin;
}

//==========================================================================
//  CheckAtrFilter - session-level gate. Requires enough recent
//  volatility for the breakout to plausibly reach its TP distance --
//  screens out dead, low-movement sessions. pipSize is passed in from
//  PlaceTokyoOrders() rather than recomputed here, since it's already
//  available there. outValPips receives the actual ATR reading in pips
//  (0 if unavailable) so the caller can log which chart/instance saw
//  what value.
//==========================================================================
bool CheckAtrFilter(double pipSize, double &outValPips)
{
   outValPips = 0.0;
   if(!UseAtrFilter) return true;
   if(atrHandle == INVALID_HANDLE) return true;
   double val[];
   if(CopyBuffer(atrHandle, 0, 1, 1, val) <= 0) return false;
   outValPips = val[0] / pipSize;
   return val[0] >= (AtrMinPips * pipSize);
}

//==========================================================================
//  GetLotSize - sizes the position so a full stop-out at slDistancePrice
//  costs a consistent RiskPercent of equity, regardless of that session's
//  actual range/offset. See the risk-management input comments above for
//  why this replaced the previous flat LotSize behavior.
//==========================================================================
double GetLotSize(double slDistancePrice)
{
   double step   = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_STEP);
   double minLot = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_MAX);
   double lots;

   if(UseRiskBasedSizing && slDistancePrice > 0.0)
   {
      double tickValue = SymbolInfoDouble(Symbol(), SYMBOL_TRADE_TICK_VALUE);
      double tickSize  = SymbolInfoDouble(Symbol(), SYMBOL_TRADE_TICK_SIZE);

      if(tickValue > 0.0 && tickSize > 0.0)
      {
         double valuePerPriceUnitPerLot = tickValue / tickSize;
         double lossPerLot   = slDistancePrice * valuePerPriceUnitPerLot;
         double riskAmount   = AccountInfoDouble(ACCOUNT_EQUITY) * (RiskPercent / 100.0);
         lots = (lossPerLot > 0.0) ? (riskAmount / lossPerLot) : LotSize;
      }
      else
      {
         lots = LotSize;   // broker didn't report tick value/size -- fall back rather than fail
      }
   }
   else
   {
      lots = LotSize;
   }

   lots = MathFloor(lots / step) * step;
   return MathMax(minLot, MathMin(maxLot, lots));
}

//==========================================================================
//  DrawSessionRange (NEW in V2.0) - draws a rectangle spanning the Tokyo
//  session's high/low from session start out to that day's hard-close
//  hour, plus a small text label showing the range size in pips. Called
//  for every session that gets evaluated, whether or not a trade is
//  ultimately taken, so you can see on the chart why a session was
//  skipped (too narrow/wide, filtered out, etc). Objects are anchored by
//  time/price, so they display correctly on any chart period, including
//  M15. Object names are tagged by session date so re-running the same
//  day (e.g. re-attaching in Strategy Tester) updates rather than
//  duplicates them.
//==========================================================================
void DrawSessionRange(datetime sessionStart, datetime sessionEnd, double high, double low, double rangePips)
{
   if(!ShowSessionRangeOnChart) return;

   string dateTag = TimeToString(sessionStart, TIME_DATE);
   StringReplace(dateTag, ".", "");
   string boxName   = "TRB_Range_" + dateTag;
   string labelName = boxName + "_Label";

   //--- Extend the box out to that day's hard-close hour for a fuller
   //    picture of the trading day; fall back to +1h past session end
   //    if that would somehow land before/at sessionEnd.
   MqlDateTime edt;
   TimeToStruct(sessionStart, edt);
   edt.hour = CloseHourGMT; edt.min = 0; edt.sec = 0;
   datetime displayEnd = StructToTime(edt) + BacktestOffset * 3600;
   if(displayEnd <= sessionEnd)
      displayEnd = sessionEnd + 3600;

   if(ObjectFind(0, boxName) < 0)
   {
      ObjectCreate(0, boxName, OBJ_RECTANGLE, 0, sessionStart, high, displayEnd, low);
      ObjectSetInteger(0, boxName, OBJPROP_COLOR, clrDodgerBlue);
      ObjectSetInteger(0, boxName, OBJPROP_STYLE, STYLE_DOT);
      ObjectSetInteger(0, boxName, OBJPROP_FILL, true);
      ObjectSetInteger(0, boxName, OBJPROP_BACK, true);
      ObjectSetInteger(0, boxName, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, boxName, OBJPROP_HIDDEN, true);
   }
   else
   {
      ObjectMove(0, boxName, 0, sessionStart, high);
      ObjectMove(0, boxName, 1, displayEnd, low);
   }

   string labelText = StringFormat("TRB %.1f pips", rangePips);
   if(ObjectFind(0, labelName) < 0)
      ObjectCreate(0, labelName, OBJ_TEXT, 0, sessionEnd, high);
   else
      ObjectMove(0, labelName, 0, sessionEnd, high);

   ObjectSetString(0, labelName, OBJPROP_TEXT, labelText);
   ObjectSetInteger(0, labelName, OBJPROP_COLOR, clrDodgerBlue);
   ObjectSetInteger(0, labelName, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, labelName, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, labelName, OBJPROP_HIDDEN, true);
}

//==========================================================================
//  PlaceTokyoOrders - calculate range and place pending stop orders
//==========================================================================
void PlaceTokyoOrders(datetime gmtNow)
{
   MqlDateTime gdt;
   TimeToStruct(gmtNow, gdt);

   //--- Session start timestamp
   gdt.hour = StartHourGMT; gdt.min = 0; gdt.sec = 0;
   datetime sessionStart = StructToTime(gdt) + BacktestOffset * 3600;

   //--- Session end timestamp
   gdt.hour = EndHourGMT;
   datetime sessionEnd = StructToTime(gdt) + BacktestOffset * 3600;

   //--- Handle midnight cross
   if(sessionStart >= sessionEnd) sessionStart -= 86400;

   //--- Fetch M1 bars for the session
   MqlRates rates[];
   int copied = CopyRates(Symbol(), PERIOD_M1, sessionStart, sessionEnd, rates);

   if(copied <= 0)
   {
      PrintFormat("TRB [Magic=%d]: CopyRates returned %d bars | %s to %s - session skipped",
                  (int)MagicNumber, copied,
                  TimeToString(sessionStart, TIME_DATE|TIME_MINUTES),
                  TimeToString(sessionEnd,   TIME_DATE|TIME_MINUTES));
      return;
   }

   //--- Session high and low
   double rangeHigh = rates[0].high;
   double rangeLow  = rates[0].low;
   for(int i = 1; i < copied; i++)
   {
      if(rates[i].high > rangeHigh) rangeHigh = rates[i].high;
      if(rates[i].low  < rangeLow)  rangeLow  = rates[i].low;
   }

   //--- Pip size
   int    digits  = (int)SymbolInfoInteger(Symbol(), SYMBOL_DIGITS);
   double pipSize = SymbolInfoDouble(Symbol(), SYMBOL_POINT) * ((digits == 5 || digits == 3) ? 10.0 : 1.0);
   double offset      = PipsOffset * pipSize;
   double rangeWidth  = rangeHigh - rangeLow;
   double rangePips   = rangeWidth / pipSize;

   PrintFormat("TRB [Magic=%d]: Session %s | High=%.5f Low=%.5f | Range=%.1f pips | Bars=%d",
               (int)MagicNumber, TimeToString(sessionStart, TIME_DATE), rangeHigh, rangeLow, rangePips, copied);

   //--- Mark this session's range on the chart regardless of whether it
   //    ends up passing the filters below, so you can see why a day was
   //    skipped just by looking at the chart.
   DrawSessionRange(sessionStart, sessionEnd, rangeHigh, rangeLow, rangePips);

   //--- Range filter
   if(rangePips < MinRangePips)
   {
      PrintFormat("TRB [Magic=%d]: SKIPPED - %.1f pips < MinRangePips %d", (int)MagicNumber, rangePips, MinRangePips);
      return;
   }
   if(MaxRangePips > 0 && rangePips > MaxRangePips)
   {
      PrintFormat("TRB [Magic=%d]: SKIPPED - %.1f pips > MaxRangePips %d", (int)MagicNumber, rangePips, MaxRangePips);
      return;
   }

   //--- ADX / ATR session-level gates - unlike the EMA filter below,
   //    these aren't direction-specific: a session either clears them or
   //    it doesn't, so a failure blocks BOTH buy and sell for the day.
   bool allowBuy  = true;
   bool allowSell = true;

   double adxVal = 0.0, atrValPips = 0.0;

   if(!CheckAdxFilter(adxVal))
   {
      PrintFormat("TRB [Magic=%d]: ADX FILTER BLOCKED - ADX=%.1f < min %.1f", (int)MagicNumber, adxVal, AdxMin);
      allowBuy = false; allowSell = false;
   }
   if(!CheckAtrFilter(pipSize, atrValPips))
   {
      PrintFormat("TRB [Magic=%d]: ATR FILTER BLOCKED - ATR=%.1f pips < min %.1f pips", (int)MagicNumber, atrValPips, AtrMinPips);
      allowBuy = false; allowSell = false;
   }

   //--- EMA trend filter
   if(UseTrendFilter && emaHandle != INVALID_HANDLE)
   {
      double emaVal[];
      ArraySetAsSeries(emaVal, true);
      int bufResult = CopyBuffer(emaHandle, 0, 0, 3, emaVal);

      if(bufResult <= 0)
      {
         PrintFormat("TRB [Magic=%d]: EMA buffer returned %d - filter bypassed (warming up)", (int)MagicNumber, bufResult);
      }
      else
      {
         double ema   = emaVal[0];
         double price = SymbolInfoDouble(Symbol(), SYMBOL_BID);
         allowBuy     = allowBuy  && (price > ema);
         allowSell    = allowSell && (price < ema);
         PrintFormat("TRB [Magic=%d]: EMA=%.5f Price=%.5f | Buy=%s Sell=%s",
                     (int)MagicNumber, ema, price,
                     allowBuy  ? "YES" : "NO",
                     allowSell ? "YES" : "NO");
      }
   }

   //--- Order levels
   double buyEntry  = NormalizeDouble(rangeHigh + offset, digits);
   double buySL     = NormalizeDouble(rangeLow  - offset, digits);
   double buyTP     = NormalizeDouble(buyEntry  + rangeWidth * TPMultiplier, digits);
   double sellEntry = NormalizeDouble(rangeLow  - offset, digits);
   double sellSL    = NormalizeDouble(rangeHigh + offset, digits);
   double sellTP    = NormalizeDouble(sellEntry - rangeWidth * TPMultiplier, digits);

   double ask = SymbolInfoDouble(Symbol(), SYMBOL_ASK);
   double bid = SymbolInfoDouble(Symbol(), SYMBOL_BID);

   if(allowBuy && buyEntry > ask)
   {
      double buyLot = GetLotSize(buyEntry - buySL);   // size off THIS session's real stop distance
      bool ok = trade.BuyStop(buyLot, buyEntry, Symbol(), buySL, buyTP,
                              ORDER_TIME_GTC, 0, StringFormat("TRB V2.0 Buy [%d]", (int)MagicNumber));
      PrintFormat("TRB [Magic=%d]: BuyStop lot=%.2f entry=%.5f SL=%.5f TP=%.5f | %s",
                  (int)MagicNumber, buyLot, buyEntry, buySL, buyTP, ok ? "PLACED" : "FAILED");
   }
   if(allowSell && sellEntry < bid)
   {
      double sellLot = GetLotSize(sellSL - sellEntry);   // size off THIS session's real stop distance
      bool ok = trade.SellStop(sellLot, sellEntry, Symbol(), sellSL, sellTP,
                               ORDER_TIME_GTC, 0, StringFormat("TRB V2.0 Sell [%d]", (int)MagicNumber));
      PrintFormat("TRB [Magic=%d]: SellStop lot=%.2f entry=%.5f SL=%.5f TP=%.5f | %s",
                  (int)MagicNumber, sellLot, sellEntry, sellSL, sellTP, ok ? "PLACED" : "FAILED");
   }
}

//==========================================================================
//  UTILITY FUNCTIONS
//==========================================================================

bool HasActivePosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
         if((ulong)PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
            PositionGetString(POSITION_SYMBOL) == Symbol())
            return true;
   }
   return false;
}

void CancelPendingOrders()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket > 0)
         if((ulong)OrderGetInteger(ORDER_MAGIC) == MagicNumber &&
            OrderGetString(ORDER_SYMBOL) == Symbol())
         {
            long type = OrderGetInteger(ORDER_TYPE);
            if(type == ORDER_TYPE_BUY_STOP || type == ORDER_TYPE_SELL_STOP)
               trade.OrderDelete(ticket);
         }
   }
}

void CloseAllActivePositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
         if((ulong)PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
            PositionGetString(POSITION_SYMBOL) == Symbol())
            trade.PositionClose(ticket);
   }
}

double OnTester()
{
   double profit = TesterStatistics(STAT_PROFIT);
   double drawdown = TesterStatistics(STAT_EQUITY_DD);
   
   // Calculates Recovery Factor. Helps optimization find settings with the best return vs drawdown ratio.
   if(drawdown > 0)
      return profit / drawdown;
      
   return profit;
}