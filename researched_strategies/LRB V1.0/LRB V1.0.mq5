//+------------------------------------------------------------------+
//|                              London_Breakout_NexGenAlgo.mq5       |
//|  NexGenAlgo Strategy Brief No.146 - "London Breakout"             |
//|  Session breakout on the Asian range (00:00-06:00 GMT),           |
//|  OCO pending stops at London open, tiered stop-loss, single        |
//|  adjustable R:R target (full close, no partial), hard time exits. |
//|                                                                    |
//|  Rules encoded (per brief, as adjusted by user decisions):        |
//|   01 Mark Asian high/low 00:00-06:00 GMT at 07:00 GMT              |
//|   02 Skip day if range < 15 pips or > 40 pips                      |
//|   03 Buy Stop 5p above high / Sell Stop 5p below low                |
//|   04 SL = opposite side of range; if range > 25 pips, tighten SL   |
//|      to a flat 20 pips from entry instead                          |
//|   05 Single TP at InpRewardToRisk x the stop distance - full       |
//|      position closes at SL or TP, no partial close/breakeven tier |
//|   06 OCO on fill; cancel both if neither fills by 09:00 GMT;        |
//|      force-close any open position at 11:00 GMT                    |
//|   07 Day-of-week filter (Mon/Fri) + manual news-filter placeholder  |
//+------------------------------------------------------------------+
#property copyright "Adapted for AlphaForge / MT5 backtesting"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//--- Session definition (all times GMT)
input group "=== Session Times (GMT) ==="
input double   InpBrokerToGMTOffsetHours = 0.0;  // GMT = Broker server time + this offset (set per broker/DST)
input int      InpAsianStartHour   = 0;    // Asian range window start, GMT hour
input int      InpAsianEndHour     = 6;    // Asian range window end, GMT hour
input int      InpSetupHour        = 7;    // Mark range + place pending orders, GMT hour
input int      InpExpiryHour       = 9;    // Cancel unfilled pending orders, GMT hour
input int      InpCloseHour        = 11;   // Force-close any open position, GMT hour

input group "=== Range Filter ==="
input double   InpMinRangePips     = 15.0; // Skip day if Asian range narrower than this
input double   InpMaxRangePips     = 40.0; // Skip day if Asian range wider than this
input double   InpWideRangeThresholdPips = 25.0; // Above this, tighten SL to flat pips instead of range-based

input group "=== Entry / Stop ==="
input double   InpBufferPips       = 5.0;  // Pending order buffer beyond Asian high/low
input double   InpTightStopPips    = 20.0; // Flat SL distance used when range > wide threshold

input group "=== Target ==="
input double   InpRewardToRisk     = 2.0;  // Reward:Risk ratio for the single take-profit (adjustable)
// Single TP, full close - no partial close, no breakeven tier

input group "=== Day / News Filters ==="
input bool     InpAvoidMonday      = true;  // Skip Mondays (gap risk)
input bool     InpAvoidFriday      = true;  // Skip Fridays (poor follow-through)
input bool     InpUseNewsFilter    = false; // Placeholder toggle - stub always passes until wired to a real calendar

input group "=== Chart Markers ==="
input bool     InpDrawRangeMarkers = true;  // Draw Asian range box/lines on chart (disable for very long backtests)

input group "=== Position Sizing ==="
input bool     InpUseRiskPercent   = true;  // true: size by % risk of balance | false: fixed lot
input double   InpRiskPercent      = 1.0;   // Risk per trade, % of account balance
input double   InpLotSize          = 0.10;  // Fixed lot size (used when InpUseRiskPercent = false, or as fallback)

input group "=== Execution ==="
input int      InpSlippage         = 20;    // Max slippage, points
input long     InpMagic            = 20260924; // Magic number

//--- Globals
CTrade   trade;

datetime g_lastDayMidnightGMT = 0;
bool     g_setupDone          = false; // true once today's 07:00 setup has been evaluated (placed or skipped)

double   g_asianHigh = 0.0, g_asianLow = 0.0;

datetime g_lastM15BarTimeForMarking = 0;
bool     g_rangeTrackingActive = false; // true while within today's Asian window, live-tracking high/low
bool     g_rangeFinalized      = false; // true once the range for today is locked in (drawn + usable for setup)
string   g_rangeBoxName        = "";
string   g_rangeStartLineName  = "";
string   g_rangeEndLineName    = "";
string   g_rangeLabelName      = "";

ulong    g_buyStopTicket  = 0;
ulong    g_sellStopTicket = 0;

double   g_buySL = 0.0, g_buyTP = 0.0;
double   g_sellSL = 0.0, g_sellTP = 0.0;

ulong    g_activeTicket   = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFillingBySymbol(_Symbol);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
}

//+------------------------------------------------------------------+
double PipSize()
{
   int    digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double point  = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   return (digits == 3 || digits == 5) ? point * 10.0 : point;
}

//+------------------------------------------------------------------+
datetime ServerToGMT(datetime srv) { return srv + (int)(InpBrokerToGMTOffsetHours * 3600); }
datetime GMTToServer(datetime gmt) { return gmt - (int)(InpBrokerToGMTOffsetHours * 3600); }

//+------------------------------------------------------------------+
bool IsNewM15BarForMarking()
{
   datetime t = iTime(_Symbol, PERIOD_M15, 0);
   if(t != g_lastM15BarTimeForMarking)
   {
      g_lastM15BarTimeForMarking = t;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
void EnsureRangeObjectNames(datetime gmtMidnight)
{
   if(g_rangeBoxName != "") return; // already allocated for today
   string dateTag = TimeToString(gmtMidnight, TIME_DATE);
   StringReplace(dateTag, ".", "");
   g_rangeBoxName       = "AsianRange_"  + dateTag;
   g_rangeStartLineName = "AsianStart_"  + dateTag;
   g_rangeEndLineName   = "AsianEnd_"    + dateTag;
   g_rangeLabelName     = "AsianLabel_"  + dateTag;
}

//+------------------------------------------------------------------+
//| Draw/lock the finalized range box + start/end lines + text label. |
//| Safe to call whether or not live tracking already created the box |
//| (fallback path when the EA didn't run through the whole window).  |
//+------------------------------------------------------------------+
void FinalizeRangeVisuals(datetime gmtMidnight)
{
   if(!InpDrawRangeMarkers) return;

   EnsureRangeObjectNames(gmtMidnight);
   datetime startSrv = GMTToServer(gmtMidnight + InpAsianStartHour * 3600);
   datetime endSrv   = GMTToServer(gmtMidnight + InpAsianEndHour   * 3600);

   if(ObjectFind(0, g_rangeBoxName) < 0)
      ObjectCreate(0, g_rangeBoxName, OBJ_RECTANGLE, 0, startSrv, g_asianHigh, endSrv, g_asianLow);
   else
   {
      ObjectSetInteger(0, g_rangeBoxName, OBJPROP_TIME, 0, startSrv);
      ObjectSetInteger(0, g_rangeBoxName, OBJPROP_TIME, 1, endSrv);
      ObjectSetDouble (0, g_rangeBoxName, OBJPROP_PRICE, 0, g_asianHigh);
      ObjectSetDouble (0, g_rangeBoxName, OBJPROP_PRICE, 1, g_asianLow);
   }
   ObjectSetInteger(0, g_rangeBoxName, OBJPROP_COLOR, clrGold);
   ObjectSetInteger(0, g_rangeBoxName, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, g_rangeBoxName, OBJPROP_FILL,  false);
   ObjectSetInteger(0, g_rangeBoxName, OBJPROP_BACK,  false);

   if(ObjectFind(0, g_rangeStartLineName) < 0)
   {
      ObjectCreate(0, g_rangeStartLineName, OBJ_VLINE, 0, startSrv, 0);
      ObjectSetInteger(0, g_rangeStartLineName, OBJPROP_COLOR, clrDodgerBlue);
      ObjectSetInteger(0, g_rangeStartLineName, OBJPROP_STYLE, STYLE_DOT);
      ObjectSetString (0, g_rangeStartLineName, OBJPROP_TOOLTIP, "Asian Range Start");
   }

   if(ObjectFind(0, g_rangeEndLineName) < 0)
   {
      ObjectCreate(0, g_rangeEndLineName, OBJ_VLINE, 0, endSrv, 0);
      ObjectSetInteger(0, g_rangeEndLineName, OBJPROP_COLOR, clrGold);
      ObjectSetInteger(0, g_rangeEndLineName, OBJPROP_STYLE, STYLE_DOT);
      ObjectSetString (0, g_rangeEndLineName, OBJPROP_TOOLTIP, "Asian Range End");
   }

   double pip       = PipSize();
   double rangePips = (g_asianHigh - g_asianLow) / pip;
   string labelText = StringFormat("Asian Range: %.1f pips (H:%.5f L:%.5f)", rangePips, g_asianHigh, g_asianLow);

   if(ObjectFind(0, g_rangeLabelName) < 0)
      ObjectCreate(0, g_rangeLabelName, OBJ_TEXT, 0, endSrv, g_asianHigh);
   ObjectSetString (0, g_rangeLabelName, OBJPROP_TEXT, labelText);
   ObjectSetInteger(0, g_rangeLabelName, OBJPROP_COLOR, clrGold);
   ObjectSetInteger(0, g_rangeLabelName, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, g_rangeLabelName, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);
}

//+------------------------------------------------------------------+
//| Live range marking: creates the box the moment the Asian window   |
//| starts, grows it with the running high/low each new M15 bar, and  |
//| finalizes it the moment the window ends.                          |
//+------------------------------------------------------------------+
void UpdateAsianRangeLive(datetime gmtMidnight, int gmtHour)
{
   if(!InpDrawRangeMarkers) return;

   bool inWindow = (gmtHour >= InpAsianStartHour && gmtHour < InpAsianEndHour);

   if(inWindow)
   {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

      if(!g_rangeTrackingActive)
      {
         g_rangeTrackingActive = true;
         g_asianHigh = bid;
         g_asianLow  = bid;
         EnsureRangeObjectNames(gmtMidnight);

         datetime startSrv = GMTToServer(gmtMidnight + InpAsianStartHour * 3600);

         ObjectCreate(0, g_rangeStartLineName, OBJ_VLINE, 0, startSrv, 0);
         ObjectSetInteger(0, g_rangeStartLineName, OBJPROP_COLOR, clrDodgerBlue);
         ObjectSetInteger(0, g_rangeStartLineName, OBJPROP_STYLE, STYLE_DOT);
         ObjectSetString (0, g_rangeStartLineName, OBJPROP_TOOLTIP, "Asian Range Start");

         ObjectCreate(0, g_rangeBoxName, OBJ_RECTANGLE, 0, startSrv, g_asianHigh, TimeCurrent(), g_asianLow);
         ObjectSetInteger(0, g_rangeBoxName, OBJPROP_COLOR, clrDodgerBlue);
         ObjectSetInteger(0, g_rangeBoxName, OBJPROP_STYLE, STYLE_DOT);
         ObjectSetInteger(0, g_rangeBoxName, OBJPROP_FILL,  false);
         ObjectSetInteger(0, g_rangeBoxName, OBJPROP_BACK,  true);
      }
      else
      {
         if(bid > g_asianHigh) g_asianHigh = bid;
         if(bid < g_asianLow)  g_asianLow  = bid;

         ObjectSetDouble (0, g_rangeBoxName, OBJPROP_PRICE, 0, g_asianHigh);
         ObjectSetDouble (0, g_rangeBoxName, OBJPROP_PRICE, 1, g_asianLow);
         ObjectSetInteger(0, g_rangeBoxName, OBJPROP_TIME,  1, TimeCurrent());
      }
   }
   else if(g_rangeTrackingActive && !g_rangeFinalized)
   {
      FinalizeRangeVisuals(gmtMidnight);
      g_rangeFinalized = true;
   }
}

//+------------------------------------------------------------------+
//| Lot sizing (same model as the HA EA): % risk of balance sized off |
//| the actual stop distance, fallback to fixed lot if unavailable.   |
//+------------------------------------------------------------------+
double CalculateLotSize(double stopDistance)
{
   if(!InpUseRiskPercent || stopDistance <= 0.0)
      return InpLotSize;

   double balance   = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = balance * (InpRiskPercent / 100.0);

   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickValue <= 0.0 || tickSize <= 0.0)
      return InpLotSize;

   double moneyPerLotAtStop = (stopDistance / tickSize) * tickValue;
   if(moneyPerLotAtStop <= 0.0)
      return InpLotSize;

   double lots = riskMoney / moneyPerLotAtStop;

   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double lotMin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lotMax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(lotStep <= 0.0) lotStep = 0.01;

   lots = MathFloor(lots / lotStep) * lotStep;
   lots = MathMax(lotMin, MathMin(lotMax, lots));
   return lots;
}

//+------------------------------------------------------------------+
//| Placeholder news filter. Currently always passes; wire a real     |
//| economic-calendar check here later. The input just toggles        |
//| whether this stub is even consulted.                              |
//+------------------------------------------------------------------+
bool PassesNewsFilter()
{
   if(!InpUseNewsFilter)
      return true;
   // TODO: hook actual calendar/manual news check here.
   return true;
}

//+------------------------------------------------------------------+
void ResetDailyState()
{
   g_setupDone   = false;
   g_asianHigh   = 0.0;
   g_asianLow    = 0.0;
   g_buyStopTicket  = 0;
   g_sellStopTicket = 0;

   g_rangeTrackingActive = false;
   g_rangeFinalized      = false;
   g_rangeBoxName        = "";
   g_rangeStartLineName  = "";
   g_rangeEndLineName    = "";
   g_rangeLabelName      = "";
}

//+------------------------------------------------------------------+
void CancelPendingIfExists(ulong &ticket)
{
   if(ticket == 0) return;
   if(OrderSelect(ticket))
      trade.OrderDelete(ticket);
   ticket = 0;
}

//+------------------------------------------------------------------+
void CancelBothPending()
{
   CancelPendingIfExists(g_buyStopTicket);
   CancelPendingIfExists(g_sellStopTicket);
}

//+------------------------------------------------------------------+
//| Fallback: recompute the Asian range from bar history. Only needed |
//| if the EA wasn't running through the live 00:00-06:00 window      |
//| today (e.g. just attached, or tester start date lands mid-window).|
//+------------------------------------------------------------------+
bool ComputeHistoricalAsianRange(datetime gmtMidnight)
{
   datetime asianStartSrv = GMTToServer(gmtMidnight + InpAsianStartHour * 3600);
   datetime asianEndSrv   = GMTToServer(gmtMidnight + InpAsianEndHour   * 3600) - 60; // exclude the 06:00 bar itself

   MqlRates rates[];
   int copied = CopyRates(_Symbol, PERIOD_M15, asianStartSrv, asianEndSrv, rates);
   if(copied <= 0)
   {
      Print("London Breakout: could not read Asian session bars, skipping day");
      return false;
   }

   double hi = rates[0].high, lo = rates[0].low;
   for(int i = 1; i < copied; i++)
   {
      if(rates[i].high > hi) hi = rates[i].high;
      if(rates[i].low  < lo) lo = rates[i].low;
   }
   g_asianHigh = hi;
   g_asianLow  = lo;
   return true;
}

//+------------------------------------------------------------------+
//| Evaluate the 07:00 GMT setup: mark range, apply filters, place    |
//| OCO pending stops (or skip the day).                              |
//+------------------------------------------------------------------+
void EvaluateSetup(datetime gmtMidnight, int gmtDayOfWeek)
{
   g_setupDone = true; // whatever happens below, don't re-evaluate today

   //--- Day-of-week filter
   if(InpAvoidMonday && gmtDayOfWeek == 1) return; // 1 = Monday
   if(InpAvoidFriday && gmtDayOfWeek == 5) return; // 5 = Friday

   //--- News filter (placeholder)
   if(!PassesNewsFilter()) return;

   //--- Use the live-tracked range if the EA ran through the window today;
   //    otherwise fall back to recomputing it from bar history.
   if(!g_rangeFinalized)
   {
      if(!ComputeHistoricalAsianRange(gmtMidnight))
         return;
      FinalizeRangeVisuals(gmtMidnight);
      g_rangeFinalized = true;
   }

   double pip = PipSize();
   double rangePips = (g_asianHigh - g_asianLow) / pip;

   //--- Range-size filter
   if(rangePips < InpMinRangePips || rangePips > InpMaxRangePips)
      return; // skip day, range not tradable

   //--- Compute entries
   double bufferPrice = InpBufferPips * pip;
   double buyEntry  = g_asianHigh + bufferPrice;
   double sellEntry = g_asianLow  - bufferPrice;

   //--- Stop placement: range-based, unless range exceeds the wide threshold
   double riskDistance;
   if(rangePips > InpWideRangeThresholdPips)
   {
      double tightStop = InpTightStopPips * pip;
      g_buySL  = buyEntry  - tightStop;
      g_sellSL = sellEntry + tightStop;
      riskDistance = tightStop;
   }
   else
   {
      g_buySL  = g_asianLow;
      g_sellSL = g_asianHigh;
      riskDistance = buyEntry - g_buySL; // symmetric to sellSL - sellEntry
   }

   //--- Single TP at InpRewardToRisk x the stop distance
   g_buyTP  = buyEntry  + riskDistance * InpRewardToRisk;
   g_sellTP = sellEntry - riskDistance * InpRewardToRisk;

   double lots = CalculateLotSize(riskDistance);
   if(lots <= 0.0) return;

   //--- Place OCO pending stops with native SL/TP (full close on either)
   if(trade.BuyStop(lots, buyEntry, _Symbol, g_buySL, g_buyTP, ORDER_TIME_SPECIFIED,
                     GMTToServer(gmtMidnight + InpExpiryHour * 3600), "LB_Buy"))
      g_buyStopTicket = trade.ResultOrder();

   if(trade.SellStop(lots, sellEntry, _Symbol, g_sellSL, g_sellTP, ORDER_TIME_SPECIFIED,
                      GMTToServer(gmtMidnight + InpExpiryHour * 3600), "LB_Sell"))
      g_sellStopTicket = trade.ResultOrder();
}

//+------------------------------------------------------------------+
//| Detect a pending order having triggered into a live position and  |
//| cancel the OCO counterpart. No partial-close/breakeven tier -     |
//| the position runs to native SL or TP set at order placement.      |
//+------------------------------------------------------------------+
void CheckForFill()
{
   if(g_activeTicket != 0) return; // already tracking a live position
   if(!PositionSelect(_Symbol)) return;
   if(PositionGetInteger(POSITION_MAGIC) != InpMagic) return;

   g_activeTicket = PositionGetInteger(POSITION_TICKET);
   bool isBuy     = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);

   //--- OCO: cancel the side that did not fill
   if(isBuy)
      CancelPendingIfExists(g_sellStopTicket);
   else
      CancelPendingIfExists(g_buyStopTicket);
}

//+------------------------------------------------------------------+
//| Position runs on its native SL/TP; this just clears tracking once |
//| it's closed (by SL, TP, or the 11:00 GMT forced close) so         |
//| CheckForFill can pick up the next fill correctly.                 |
//+------------------------------------------------------------------+
void CheckPositionStillOpen()
{
   if(g_activeTicket == 0) return;
   if(!PositionSelectByTicket(g_activeTicket))
      g_activeTicket = 0;
}

//+------------------------------------------------------------------+
void OnTick()
{
   datetime gmtNow = ServerToGMT(TimeCurrent());
   MqlDateTime gmtStruct;
   TimeToStruct(gmtNow, gmtStruct);

   MqlDateTime midStruct = gmtStruct;
   midStruct.hour = 0; midStruct.min = 0; midStruct.sec = 0;
   datetime gmtMidnight = StructToTime(midStruct);

   //--- New GMT day: reset state (any leftover pendings should already be
   //    gone via expiry/fill, but clear defensively)
   if(gmtMidnight != g_lastDayMidnightGMT)
   {
      if(g_activeTicket == 0) // don't nuke a still-open overnight-tracked position
         CancelBothPending();
      g_lastDayMidnightGMT = gmtMidnight;
      ResetDailyState();
   }

   //--- Live-track and draw the Asian range as it forms (once per new M15 bar)
   if(IsNewM15BarForMarking())
      UpdateAsianRangeLive(gmtMidnight, gmtStruct.hour);

   //--- 1. Run the 07:00 GMT setup once per day
   if(!g_setupDone && gmtStruct.hour >= InpSetupHour)
      EvaluateSetup(gmtMidnight, gmtStruct.day_of_week);

   //--- 2. Detect a fill, handle OCO cancellation, and track position lifecycle
   CheckForFill();
   CheckPositionStillOpen();

   //--- 3. Expiry: cancel unfilled pendings at 09:00 GMT
   if(gmtStruct.hour >= InpExpiryHour && (g_buyStopTicket != 0 || g_sellStopTicket != 0))
      CancelBothPending();

   //--- 4. Hard close: force-exit any open position at 11:00 GMT regardless of P&L
   if(gmtStruct.hour >= InpCloseHour && g_activeTicket != 0)
   {
      if(PositionSelectByTicket(g_activeTicket))
         trade.PositionClose(g_activeTicket);
      g_activeTicket = 0;
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

//+------------------------------------------------------------------+