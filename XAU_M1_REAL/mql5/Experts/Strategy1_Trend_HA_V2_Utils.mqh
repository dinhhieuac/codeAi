//+------------------------------------------------------------------+
//| Strategy1_Trend_HA_V2_Utils.mqh                                  |
//| Helpers converted from XAU_M1_REAL/utils.py + strategy logic       |
//+------------------------------------------------------------------+
#ifndef STRATEGY1_TREND_HA_V2_UTILS_MQH
#define STRATEGY1_TREND_HA_V2_UTILS_MQH

//--- Heiken Ashi bar
struct HaBar
{
   double ha_open;
   double ha_high;
   double ha_low;
   double ha_close;
   double sma55_high;
   double sma55_low;
   double rsi;
   double atr;
   long   tick_volume;
   double vol_ma;
};

int S1_ParseTimeToMinutes(const string time_str);
double S1_CalcSMAFromLong(const long &values[], const int size, const int period, const int shift);

//+------------------------------------------------------------------+
double S1_PipSize(const string symbol)
{
   const double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   string upper = symbol;
   StringToUpper(upper);
   if(StringFind(upper, "XAU") >= 0 || StringFind(upper, "GOLD") >= 0)
   {
      if(point >= 0.01)
         return point;
      return point * 10.0;
   }
   return point * 10.0;
}

//+------------------------------------------------------------------+
double S1_PipsToPrice(const string symbol, const double pips)
{
   return pips * S1_PipSize(symbol);
}

//+------------------------------------------------------------------+
ENUM_ORDER_TYPE_FILLING S1_GetFillingMode(const string symbol)
{
   const long mode = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      return ORDER_FILLING_FOK;
   if((mode & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}

//+------------------------------------------------------------------+
bool S1_IsDoji(const double open, const double high, const double low, const double close,
               const double threshold = 0.2)
{
   const double body = MathAbs(close - open);
   const double range = high - low;
   if(range <= 0.0)
      return true;
   return body <= range * threshold;
}

//+------------------------------------------------------------------+
double S1_CalcRSI(const double &close[], const int size, const int period, const int shift)
{
   if(size < period + shift + 2)
      return 50.0;

   double avg_gain = 0.0;
   double avg_loss = 0.0;
   const int start = size - shift - period - 1;
   for(int i = start; i < start + period; i++)
   {
      const double delta = close[i + 1] - close[i];
      if(delta > 0.0)
         avg_gain += delta;
      else
         avg_loss -= delta;
   }
   avg_gain /= period;
   avg_loss /= period;
   if(avg_loss == 0.0)
      return 100.0;

   for(int i = start + period; i < size - shift - 1; i++)
   {
      const double delta = close[i + 1] - close[i];
      const double gain = (delta > 0.0) ? delta : 0.0;
      const double loss = (delta < 0.0) ? -delta : 0.0;
      avg_gain = (avg_gain * (period - 1) + gain) / period;
      avg_loss = (avg_loss * (period - 1) + loss) / period;
   }

   if(avg_loss == 0.0)
      return 100.0;
   const double rs = avg_gain / avg_loss;
   return 100.0 - (100.0 / (1.0 + rs));
}

//+------------------------------------------------------------------+
double S1_CalcATR(const double &high[], const double &low[], const double &close[],
                  const int size, const int period, const int shift)
{
   if(size < period + shift + 2)
      return 0.0;

   double sum = 0.0;
   const int start = size - shift - period;
   for(int i = start; i < size - shift; i++)
   {
      const double tr0 = high[i] - low[i];
      const double tr1 = MathAbs(high[i] - close[i - 1]);
      const double tr2 = MathAbs(low[i] - close[i - 1]);
      sum += MathMax(tr0, MathMax(tr1, tr2));
   }
   return sum / period;
}

//+------------------------------------------------------------------+
double S1_CalcADX(const double &high[], const double &low[], const double &close[],
                  const int size, const int period, const int shift)
{
   if(size < period * 2 + shift + 2)
      return 0.0;

   double tr_sum = 0.0;
   double dm_plus_sum = 0.0;
   double dm_minus_sum = 0.0;
   const int end = size - shift - 1;
   const int start = end - period;

   for(int i = start + 1; i <= end; i++)
   {
      const double up = high[i] - high[i - 1];
      const double down = low[i - 1] - low[i];
      double dm_plus = 0.0;
      double dm_minus = 0.0;
      if(up > down && up > 0.0)
         dm_plus = up;
      if(down > up && down > 0.0)
         dm_minus = down;

      const double tr0 = high[i] - low[i];
      const double tr1 = MathAbs(high[i] - close[i - 1]);
      const double tr2 = MathAbs(low[i] - close[i - 1]);
      tr_sum += MathMax(tr0, MathMax(tr1, tr2));
      dm_plus_sum += dm_plus;
      dm_minus_sum += dm_minus;
   }

   if(tr_sum <= 0.0)
      return 0.0;

   const double di_plus = 100.0 * dm_plus_sum / tr_sum;
   const double di_minus = 100.0 * dm_minus_sum / tr_sum;
   const double denom = di_plus + di_minus;
   if(denom <= 0.0)
      return 0.0;
   return 100.0 * MathAbs(di_plus - di_minus) / denom;
}

//+------------------------------------------------------------------+
double S1_CalcEMA(const double &values[], const int size, const int period, const int shift)
{
   if(size < period + shift)
      return 0.0;

   const int start = size - shift - period;
   double ema = 0.0;
   for(int i = start; i < start + period; i++)
      ema += values[i];
   ema /= period;

   const double k = 2.0 / (period + 1.0);
   for(int i = start + period; i < size - shift; i++)
      ema = values[i] * k + ema * (1.0 - k);

   return ema;
}

//+------------------------------------------------------------------+
double S1_CalcSMA(const double &values[], const int size, const int period, const int shift)
{
   if(size < period + shift)
      return 0.0;
   double sum = 0.0;
   const int start = size - shift - period;
   for(int i = start; i < size - shift; i++)
      sum += values[i];
   return sum / period;
}

//+------------------------------------------------------------------+
bool S1_BuildHaBars(const string symbol, const ENUM_TIMEFRAMES tf, const int bars_needed,
                    HaBar &ha[], int &count, const int start_shift = 0)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   const int copied = CopyRates(symbol, tf, start_shift, bars_needed, rates);
   if(copied < bars_needed)
      return false;

   count = copied;
   ArrayResize(ha, count);

   double prev_ha_open = (rates[0].open + rates[0].close) / 2.0;
   double prev_ha_close = (rates[0].open + rates[0].high + rates[0].low + rates[0].close) / 4.0;

   double close_arr[];
   ArrayResize(close_arr, count);
   for(int i = 0; i < count; i++)
      close_arr[i] = rates[i].close;

   for(int i = 0; i < count; i++)
   {
      const double ha_close = (rates[i].open + rates[i].high + rates[i].low + rates[i].close) / 4.0;
      double ha_open;
      if(i == 0)
         ha_open = (rates[i].open + rates[i].close) / 2.0;
      else
         ha_open = (ha[i - 1].ha_open + ha[i - 1].ha_close) / 2.0;

      ha[i].ha_close = ha_close;
      ha[i].ha_open = ha_open;
      ha[i].ha_high = MathMax(rates[i].high, MathMax(ha_open, ha_close));
      ha[i].ha_low = MathMin(rates[i].low, MathMin(ha_open, ha_close));
      ha[i].tick_volume = rates[i].tick_volume;

      double high_arr[];
      double low_arr[];
      ArrayResize(high_arr, i + 1);
      ArrayResize(low_arr, i + 1);
      for(int j = 0; j <= i; j++)
      {
         high_arr[j] = rates[j].high;
         low_arr[j] = rates[j].low;
      }
      ha[i].sma55_high = (i >= 54) ? S1_CalcSMA(high_arr, i + 1, 55, 0) : 0.0;
      ha[i].sma55_low = (i >= 54) ? S1_CalcSMA(low_arr, i + 1, 55, 0) : 0.0;
      ha[i].rsi = S1_CalcRSI(close_arr, i + 1, 14, 0);
   }

   double high_all[];
   double low_all[];
   double close_all[];
   ArrayResize(high_all, count);
   ArrayResize(low_all, count);
   ArrayResize(close_all, count);
   for(int i = 0; i < count; i++)
   {
      high_all[i] = rates[i].high;
      low_all[i] = rates[i].low;
      close_all[i] = rates[i].close;
   }

   for(int i = 0; i < count; i++)
   {
      ha[i].atr = S1_CalcATR(high_all, low_all, close_all, i + 1, 14, 0);
      long vol_arr[];
      ArrayResize(vol_arr, i + 1);
      for(int j = 0; j <= i; j++)
         vol_arr[j] = rates[j].tick_volume;
      ha[i].vol_ma = (i >= 9) ? (double)S1_CalcSMAFromLong(vol_arr, i + 1, 10, 0) : 0.0;
   }

   return true;
}

//+------------------------------------------------------------------+
double S1_CalcSMAFromLong(const long &values[], const int size, const int period, const int shift)
{
   if(size < period + shift)
      return 0.0;
   double sum = 0.0;
   const int start = size - shift - period;
   for(int i = start; i < size - shift; i++)
      sum += (double)values[i];
   return sum / period;
}

//+------------------------------------------------------------------+
bool S1_CheckTradingSession(const string allowed_sessions)
{
   if(allowed_sessions == "ALL" || allowed_sessions == "")
      return true;

   string parts[];
   if(StringSplit(allowed_sessions, '-', parts) != 2)
      return true;

   const int start_min = S1_ParseTimeToMinutes(parts[0]);
   const int end_min = S1_ParseTimeToMinutes(parts[1]);
   if(start_min < 0 || end_min < 0)
      return true;

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   const int now_min = dt.hour * 60 + dt.min;

   if(start_min <= end_min)
      return (now_min >= start_min && now_min <= end_min);
   return (now_min >= start_min || now_min <= end_min);
}

//+------------------------------------------------------------------+
int S1_ParseTimeToMinutes(const string time_str)
{
   string t = time_str;
   StringTrimLeft(t);
   StringTrimRight(t);
   string parts[];
   if(StringSplit(t, ':', parts) != 2)
      return -1;
   return (int)StringToInteger(parts[0]) * 60 + (int)StringToInteger(parts[1]);
}

//+------------------------------------------------------------------+
bool S1_CheckConsecutiveLosses(const string symbol, const long magic, const int limit,
                               const int lookback_hours, string &msg)
{
   if(limit <= 0)
   {
      msg = "Disabled";
      return false;
   }

   const datetime from_time = TimeCurrent() - lookback_hours * 3600;
   if(!HistorySelect(from_time, TimeCurrent()))
   {
      msg = "No recent history";
      return false;
   }

   datetime deal_times[];
   double deal_profits[];
   int deal_count = 0;

   const int total = HistoryDealsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      const ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != symbol)
         continue;
      if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != magic)
         continue;
      if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_OUT)
         continue;

      ArrayResize(deal_times, deal_count + 1);
      ArrayResize(deal_profits, deal_count + 1);
      deal_times[deal_count] = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
      deal_profits[deal_count] = HistoryDealGetDouble(ticket, DEAL_PROFIT)
                               + HistoryDealGetDouble(ticket, DEAL_SWAP)
                               + HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      deal_count++;
      if(deal_count >= limit)
         break;
   }

   if(deal_count < limit)
   {
      msg = StringFormat("Not enough trades (%d < %d)", deal_count, limit);
      return false;
   }

   int consecutive = 0;
   for(int i = 0; i < limit; i++)
   {
      if(deal_profits[i] < 0.0)
         consecutive++;
      else
         break;
   }

   if(consecutive >= limit)
   {
      msg = StringFormat("STOP: %d consecutive losses", consecutive);
      return true;
   }

   msg = StringFormat("OK: %d consecutive losses", consecutive);
   return false;
}

//+------------------------------------------------------------------+
double S1_FindSwingLow(const double &low[], const int size, const int lookback)
{
   if(size < lookback + 2)
      return 0.0;
   double min_val = low[size - lookback - 1];
   for(int i = size - lookback; i <= size - 2; i++)
      min_val = MathMin(min_val, low[i]);
   return min_val;
}

//+------------------------------------------------------------------+
double S1_FindSwingHigh(const double &high[], const int size, const int lookback)
{
   if(size < lookback + 2)
      return 0.0;
   double max_val = high[size - lookback - 1];
   for(int i = size - lookback; i <= size - 2; i++)
      max_val = MathMax(max_val, high[i]);
   return max_val;
}

//+------------------------------------------------------------------+
bool S1_CheckLiquiditySweepBuy(const double open, const double high, const double low, const double close,
                               const double &lows[], const int size, const double atr_val,
                               const string symbol, const double buffer_pips,
                               const double wick_multiplier, string &msg)
{
   if(size < 20)
   {
      msg = "Not enough data";
      return false;
   }

   const double prev_swing = S1_FindSwingLow(lows, size, 20);
   const double buffer = buffer_pips * S1_PipSize(symbol);
   const double lower_wick = MathMin(open, close) - low;
   const double wick_threshold = wick_multiplier * atr_val;

   if(low < prev_swing - buffer)
   {
      if(lower_wick >= wick_threshold)
      {
         if(close > open)
         {
            msg = "Sweep confirmed BUY";
            return true;
         }
         msg = "Sweep low OK but not bullish";
         return false;
      }
      msg = "Sweep low OK but wick too small";
      return false;
   }
   msg = "No sweep yet";
   return false;
}

//+------------------------------------------------------------------+
bool S1_CheckLiquiditySweepSell(const double open, const double high, const double low, const double close,
                                const double &highs[], const int size, const double atr_val,
                                const string symbol, const double buffer_pips,
                                const double wick_multiplier, string &msg)
{
   if(size < 20)
   {
      msg = "Not enough data";
      return false;
   }

   const double prev_swing = S1_FindSwingHigh(highs, size, 20);
   const double buffer = buffer_pips * S1_PipSize(symbol);
   const double upper_wick = high - MathMax(open, close);
   const double wick_threshold = wick_multiplier * atr_val;

   if(high > prev_swing + buffer)
   {
      if(upper_wick >= wick_threshold)
      {
         if(close < open)
         {
            msg = "Sweep confirmed SELL";
            return true;
         }
         msg = "Sweep high OK but not bearish";
         return false;
      }
      msg = "Sweep high OK but wick too small";
      return false;
   }
   msg = "No sweep yet";
   return false;
}

//+------------------------------------------------------------------+
bool S1_CheckDisplacement(const double open, const double close,
                          const double &high[], const double &low[], const int size,
                          const double atr_val, const bool is_buy,
                          const double body_multiplier, string &msg)
{
   if(size < 10)
   {
      msg = "Not enough data";
      return false;
   }

   const double body = MathAbs(close - open);
   double prev_high = high[size - 10];
   double prev_low = low[size - 10];
   for(int i = size - 9; i <= size - 2; i++)
   {
      prev_high = MathMax(prev_high, high[i]);
      prev_low = MathMin(prev_low, low[i]);
   }

   const double threshold = body_multiplier * atr_val;
   if(is_buy)
   {
      if(body >= threshold && close > prev_high)
      {
         msg = "Displacement BUY OK";
         return true;
      }
   }
   else
   {
      if(body >= threshold && close < prev_low)
      {
         msg = "Displacement SELL OK";
         return true;
      }
   }
   msg = "No displacement";
   return false;
}

//+------------------------------------------------------------------+
bool S1_CheckChopRange(const MqlRates &rates[], const int size, const double atr_val,
                       const int lookback, const double body_threshold,
                       const double overlap_threshold, string &msg)
{
   if(size < lookback)
   {
      msg = "Not enough data";
      return false;
   }

   double body_sum = 0.0;
   for(int i = size - lookback; i < size; i++)
      body_sum += MathAbs(rates[i].close - rates[i].open);
   const double body_avg = body_sum / lookback;

   double overlap_sum = 0.0;
   int pairs = 0;
   for(int i = size - lookback; i < size - 1; i++)
   {
      const double overlap_low = MathMax(rates[i].low, rates[i + 1].low);
      const double overlap_high = MathMin(rates[i].high, rates[i + 1].high);
      if(overlap_low < overlap_high)
      {
         const double overlap_size = overlap_high - overlap_low;
         const double range1 = rates[i].high - rates[i].low;
         const double range2 = rates[i + 1].high - rates[i + 1].low;
         const double avg_range = (range1 + range2) / 2.0;
         if(avg_range > 0.0)
         {
            overlap_sum += overlap_size / avg_range;
            pairs++;
         }
      }
   }

   const double avg_overlap = (pairs > 0) ? overlap_sum / pairs : 0.0;
   const bool body_cond = body_avg < body_threshold * atr_val;
   const bool overlap_cond = avg_overlap > overlap_threshold;

   if(body_cond && overlap_cond)
   {
      msg = StringFormat("CHOP body_avg=%.2f overlap=%.1f%%", body_avg, avg_overlap * 100.0);
      return true;
   }
   msg = StringFormat("Not CHOP body_avg=%.2f overlap=%.1f%%", body_avg, avg_overlap * 100.0);
   return false;
}

//+------------------------------------------------------------------+
bool S1_CheckAtrVolatility(const double &atr_values[], const int size, const double current_atr,
                           const int lookback, const double min_mult, const double max_mult,
                           string &msg)
{
   if(size < lookback + 1 || current_atr <= 0.0)
   {
      msg = "Skip ATR filter (insufficient data)";
      return true;
   }

   double sum = 0.0;
   int cnt = 0;
   for(int i = size - lookback - 1; i <= size - 2; i++)
   {
      if(atr_values[i] > 0.0)
      {
         sum += atr_values[i];
         cnt++;
      }
   }
   if(cnt == 0)
   {
      msg = "Skip ATR filter";
      return true;
   }

   const double avg_atr = sum / cnt;
   const double min_th = avg_atr * min_mult;
   const double max_th = avg_atr * max_mult;

   if(current_atr < min_th)
   {
      msg = StringFormat("ATR too low %.2f < %.2f", current_atr, min_th);
      return false;
   }
   if(current_atr > max_th)
   {
      msg = StringFormat("ATR too high %.2f > %.2f", current_atr, max_th);
      return false;
   }
   msg = StringFormat("ATR OK %.2f in [%.2f, %.2f]", current_atr, min_th, max_th);
   return true;
}

//+------------------------------------------------------------------+
int S1_CountPositions(const string symbol, const long magic)
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != magic)
         continue;
      count++;
   }
   return count;
}

//+------------------------------------------------------------------+
datetime S1_LastPositionOpenTime(const string symbol, const long magic)
{
   datetime last_time = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != magic)
         continue;
      const datetime t = (datetime)PositionGetInteger(POSITION_TIME);
      if(t > last_time)
         last_time = t;
   }
   return last_time;
}

#endif
