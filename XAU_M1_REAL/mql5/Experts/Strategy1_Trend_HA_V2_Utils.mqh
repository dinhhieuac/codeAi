//+------------------------------------------------------------------+
//| Strategy1_Trend_HA_V2_Utils.mqh                                  |
//| Helpers — parity with XAU_M1_REAL/utils.py + strategy_1_trend_ha_v2|
//+------------------------------------------------------------------+
#ifndef STRATEGY1_TREND_HA_V2_UTILS_MQH
#define STRATEGY1_TREND_HA_V2_UTILS_MQH

#include <Trade/Trade.mqh>

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
   double m1_open;
   double m1_high;
   double m1_low;
   double m1_close;
};

struct S1TrailConfig
{
   bool     trailing_enabled;
   bool     breakeven_enabled;
   string   breakeven_trigger_pips;
   double   breakeven_trigger_percent;
   string   trailing_trigger_pips;
   double   trailing_trigger_multiplier;
   string   trailing_mode;
   string   trailing_atr_timeframe;
   double   trailing_distance_pips;
   double   trailing_atr_multiplier;
   double   trailing_min_pips;
   double   trailing_max_pips;
};

int    S1_ParseTimeToMinutes(const string time_str);
double S1_CalcSMAFromLong(const long &values[], const int size, const int period, const int shift);

// Python strategy: buffer_pips * point * 10 (liquidity sweep, fixed sl/tp)
double S1_PipSizeStrategy(const string symbol)
{
   const double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   return point * 10.0;
}

// Python utils.manage_position pip convention
double S1_PipSizeManage(const string symbol)
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

double S1_PipsToPriceStrategy(const string symbol, const double pips)
{
   return pips * S1_PipSizeStrategy(symbol);
}

ENUM_ORDER_TYPE_FILLING S1_GetFillingMode(const string symbol)
{
   const long mode = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      return ORDER_FILLING_FOK;
   if((mode & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}

bool S1_IsDoji(const double open, const double high, const double low, const double close,
               const double threshold = 0.2)
{
   const double body = MathAbs(close - open);
   const double range = high - low;
   if(range <= 0.0)
      return true;
   return body <= range * threshold;
}

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

// ADX = rolling mean of DX (matches pandas calculate_adx)
double S1_CalcADX(const double &high[], const double &low[], const double &close[],
                  const int size, const int period, const int shift)
{
   if(size < period * 2 + shift + 1)
      return 0.0;

   const int target = size - shift - 1;
   double dx[];
   ArrayResize(dx, size);
   ArrayInitialize(dx, 0.0);

   for(int i = 1; i < size; i++)
   {
      if(i < period)
         continue;

      double tr_sum = 0.0;
      double dm_plus_sum = 0.0;
      double dm_minus_sum = 0.0;

      for(int j = i - period + 1; j <= i; j++)
      {
         const double up = high[j] - high[j - 1];
         const double down = low[j - 1] - low[j];
         double dm_plus = 0.0;
         double dm_minus = 0.0;
         if(up > down && up > 0.0)
            dm_plus = up;
         if(down > up && down > 0.0)
            dm_minus = down;

         const double tr0 = high[j] - low[j];
         const double tr1 = MathAbs(high[j] - close[j - 1]);
         const double tr2 = MathAbs(low[j] - close[j - 1]);
         tr_sum += MathMax(tr0, MathMax(tr1, tr2));
         dm_plus_sum += dm_plus;
         dm_minus_sum += dm_minus;
      }

      if(tr_sum <= 0.0)
         continue;

      const double di_plus = 100.0 * dm_plus_sum / tr_sum;
      const double di_minus = 100.0 * dm_minus_sum / tr_sum;
      const double denom = di_plus + di_minus;
      if(denom > 0.0)
         dx[i] = 100.0 * MathAbs(di_plus - di_minus) / denom;
   }

   if(target < period * 2 - 1)
      return 0.0;

   double adx_sum = 0.0;
   for(int i = target - period + 1; i <= target; i++)
      adx_sum += dx[i];
   return adx_sum / period;
}

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

bool S1_CopyRatesChrono(const string symbol, const ENUM_TIMEFRAMES tf, const int count,
                        MqlRates &rates[], int &copied, const int min_required = 1)
{
   ArraySetAsSeries(rates, false);
   copied = CopyRates(symbol, tf, 0, count, rates);
   return (copied >= min_required);
}

bool S1_BuildHaBars(const string symbol, const ENUM_TIMEFRAMES tf, const int bars_needed,
                    HaBar &ha[], int &count, const int atr_period = 14,
                    const int rsi_period = 14, const int start_shift = 0)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   const int copied = CopyRates(symbol, tf, start_shift, bars_needed, rates);
   if(copied < 55)
      return false;

   count = copied;
   ArrayResize(ha, count);

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
      ha[i].m1_open = rates[i].open;
      ha[i].m1_high = rates[i].high;
      ha[i].m1_low = rates[i].low;
      ha[i].m1_close = rates[i].close;

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
      ha[i].rsi = S1_CalcRSI(close_arr, i + 1, rsi_period, 0);
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
      ha[i].atr = S1_CalcATR(high_all, low_all, close_all, i + 1, atr_period, 0);
      long vol_arr[];
      ArrayResize(vol_arr, i + 1);
      for(int j = 0; j <= i; j++)
         vol_arr[j] = rates[j].tick_volume;
      ha[i].vol_ma = (i >= 9) ? S1_CalcSMAFromLong(vol_arr, i + 1, 10, 0) : 0.0;
   }

   return true;
}

bool S1_CheckTradingSession(const string symbol, const string allowed_sessions, string &msg)
{
   if(allowed_sessions == "ALL" || allowed_sessions == "")
   {
      msg = "All sessions allowed";
      return true;
   }

   string parts[];
   if(StringSplit(allowed_sessions, '-', parts) != 2)
   {
      msg = "Session check skipped (parse error)";
      return true;
   }

   const int start_min = S1_ParseTimeToMinutes(parts[0]);
   const int end_min = S1_ParseTimeToMinutes(parts[1]);
   if(start_min < 0 || end_min < 0)
   {
      msg = "Session check skipped (parse error)";
      return true;
   }

   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick))
   {
      msg = "Session check skipped (no tick)";
      return true;
   }

   // Python: datetime.fromtimestamp(tick.time) -> PC local time (NOT broker server time)
   const long local_offset = (long)(TimeLocal() - TimeCurrent());
   const datetime local_time = (datetime)((long)tick.time + local_offset);

   MqlDateTime dt;
   TimeToStruct(local_time, dt);
   const int now_min = dt.hour * 60 + dt.min;
   string start_str = parts[0];
   string end_str = parts[1];

   if(start_min <= end_min)
   {
      if(now_min >= start_min && now_min <= end_min)
      {
         msg = StringFormat("In session (%s-%s)", start_str, end_str);
         return true;
      }
      msg = StringFormat("Out of session (%s-%s), Current: %02d:%02d", start_str, end_str, dt.hour, dt.min);
      return false;
   }

   if(now_min >= start_min || now_min <= end_min)
   {
      msg = StringFormat("In session (%s-%s)", start_str, end_str);
      return true;
   }
   msg = StringFormat("Out of session (%s-%s), Current: %02d:%02d", start_str, end_str, dt.hour, dt.min);
   return false;
}

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
   for(int i = 0; i < total; i++)
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
      deal_profits[deal_count] = HistoryDealGetDouble(ticket, DEAL_PROFIT);
      deal_count++;
   }

   if(deal_count < limit)
   {
      msg = StringFormat("Not enough trades (%d < %d)", deal_count, limit);
      return false;
   }

   for(int i = 0; i < deal_count - 1; i++)
   {
      for(int j = i + 1; j < deal_count; j++)
      {
         if(deal_times[j] > deal_times[i])
         {
            const datetime tmp_t = deal_times[i];
            deal_times[i] = deal_times[j];
            deal_times[j] = tmp_t;
            const double tmp_p = deal_profits[i];
            deal_profits[i] = deal_profits[j];
            deal_profits[j] = tmp_p;
         }
      }
   }

   int consecutive = 0;
   string details = "";
   for(int i = 0; i < limit; i++)
   {
      if(deal_profits[i] < 0.0)
      {
         consecutive++;
         if(details != "")
            details += ", ";
         details += DoubleToString(deal_profits[i], 2);
      }
      else
         break;
   }

   if(consecutive >= limit)
   {
      msg = StringFormat("STOP: %d consecutive losses (%s)", consecutive, details);
      return true;
   }

   msg = StringFormat("OK: %d consecutive losses", consecutive);
   return false;
}

double S1_FindSwingLow(const double &low[], const int size, const int lookback)
{
   if(size < lookback + 2)
      return 0.0;
   double min_val = low[size - lookback - 1];
   for(int i = size - lookback; i <= size - 2; i++)
      min_val = MathMin(min_val, low[i]);
   return min_val;
}

double S1_FindSwingHigh(const double &high[], const int size, const int lookback)
{
   if(size < lookback + 2)
      return 0.0;
   double max_val = high[size - lookback - 1];
   for(int i = size - lookback; i <= size - 2; i++)
      max_val = MathMax(max_val, high[i]);
   return max_val;
}

bool S1_CheckLiquiditySweepBuy(const double open, const double high, const double low, const double close,
                               const double &lows[], const int size, const double atr_val,
                               const string symbol, const double buffer_pips,
                               const double wick_multiplier, string &msg)
{
   if(size < 20)
   {
      msg = "Khong du du lieu";
      return false;
   }

   const double prev_swing = S1_FindSwingLow(lows, size, 20);
   const double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   const double buffer = buffer_pips * point * 10.0;
   const double lower_wick = MathMin(open, close) - low;
   const double wick_threshold = wick_multiplier * atr_val;

   if(low < prev_swing - buffer)
   {
      if(lower_wick >= wick_threshold)
      {
         if(close > open)
         {
            msg = StringFormat("Sweep confirmed: Low %.2f < %.2f", low, prev_swing);
            return true;
         }
         msg = "Sweep low OK nhung nen khong bullish";
         return false;
      }
      msg = StringFormat("Sweep low OK nhung wick %.2f < %.2f", lower_wick, wick_threshold);
      return false;
   }
   msg = StringFormat("Chua sweep: Low %.2f >= %.2f", low, prev_swing - buffer);
   return false;
}

bool S1_CheckLiquiditySweepSell(const double open, const double high, const double low, const double close,
                                const double &highs[], const int size, const double atr_val,
                                const string symbol, const double buffer_pips,
                                const double wick_multiplier, string &msg)
{
   if(size < 20)
   {
      msg = "Khong du du lieu";
      return false;
   }

   const double prev_swing = S1_FindSwingHigh(highs, size, 20);
   const double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   const double buffer = buffer_pips * point * 10.0;
   const double upper_wick = high - MathMax(open, close);
   const double wick_threshold = wick_multiplier * atr_val;

   if(high > prev_swing + buffer)
   {
      if(upper_wick >= wick_threshold)
      {
         if(close < open)
         {
            msg = StringFormat("Sweep confirmed: High %.2f > %.2f", high, prev_swing);
            return true;
         }
         msg = "Sweep high OK nhung nen khong bearish";
         return false;
      }
      msg = StringFormat("Sweep high OK nhung wick %.2f < %.2f", upper_wick, wick_threshold);
      return false;
   }
   msg = StringFormat("Chua sweep: High %.2f <= %.2f", high, prev_swing + buffer);
   return false;
}

bool S1_CheckDisplacement(const double open, const double close,
                          const double &high[], const double &low[], const int size,
                          const double atr_val, const bool is_buy,
                          const double body_multiplier, string &msg)
{
   if(size < 10)
   {
      msg = "Khong du du lieu";
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
         msg = "Displacement confirmed BUY";
         return true;
      }
      msg = "No displacement BUY";
      return false;
   }

   if(body >= threshold && close < prev_low)
   {
      msg = "Displacement confirmed SELL";
      return true;
   }
   msg = "No displacement SELL";
   return false;
}

bool S1_CheckChopRange(MqlRates &rates[], const int size, const double atr_val,
                       const int lookback, const double body_threshold,
                       const double overlap_threshold, string &msg)
{
   if(size < lookback)
   {
      msg = "Khong du du lieu";
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
      msg = StringFormat("CHOP: body_avg=%.2f overlap=%.1f%%", body_avg, avg_overlap * 100.0);
      return true;
   }
   msg = StringFormat("Not CHOP: body_avg=%.2f overlap=%.1f%%", body_avg, avg_overlap * 100.0);
   return false;
}

bool S1_CheckAtrVolatility(const double &atr_values[], const int size, const double current_atr,
                           const int lookback_period, const int atr_period,
                           const double min_mult, const double max_mult,
                           const bool use_relative, const double min_absolute, const double max_absolute,
                           const bool has_min_abs, const bool has_max_abs, string &msg)
{
   if(current_atr <= 0.0)
   {
      msg = "ATR khong hop le, bo qua filter";
      return true;
   }

   if(size < MathMax(lookback_period, atr_period))
   {
      msg = "Khong du du lieu de kiem tra ATR";
      return true;
   }

   if(use_relative)
   {
      if(size < lookback_period + 1)
      {
         msg = "Khong du du lieu de kiem tra ATR";
         return true;
      }

      double sum = 0.0;
      int cnt = 0;
      for(int i = size - lookback_period - 1; i <= size - 2; i++)
      {
         if(atr_values[i] > 0.0)
         {
            sum += atr_values[i];
            cnt++;
         }
      }
      if(cnt == 0)
      {
         msg = "Khong du du lieu ATR de so sanh";
         return true;
      }

      const double avg_atr = sum / cnt;
      if(avg_atr <= 0.0)
      {
         msg = "ATR trung binh khong hop le, bo qua filter";
         return true;
      }

      const double min_th = avg_atr * min_mult;
      const double max_th = avg_atr * max_mult;

      if(current_atr < min_th)
      {
         msg = StringFormat("ATR qua thap: %.2f < %.2f", current_atr, min_th);
         return false;
      }
      if(current_atr > max_th)
      {
         msg = StringFormat("ATR qua cao: %.2f > %.2f", current_atr, max_th);
         return false;
      }
      msg = StringFormat("ATR OK: %.2f trong [%.2f, %.2f]", current_atr, min_th, max_th);
      return true;
   }

   if(has_min_abs && current_atr < min_absolute)
   {
      msg = StringFormat("ATR qua thap: %.2f < %.2f", current_atr, min_absolute);
      return false;
   }
   if(has_max_abs && current_atr > max_absolute)
   {
      msg = StringFormat("ATR qua cao: %.2f > %.2f", current_atr, max_absolute);
      return false;
   }
   msg = StringFormat("ATR OK: %.2f", current_atr);
   return true;
}

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

bool S1_StringEqualsIgnoreCase(const string a, const string b)
{
   string ua = a, ub = b;
   StringToUpper(ua);
   StringToUpper(ub);
   return ua == ub;
}

bool S1_IsAutoPips(const string value)
{
   string v = value;
   StringTrimLeft(v);
   StringTrimRight(v);
   StringToLower(v);
   return v == "auto";
}

void S1_ManagePosition(const ulong ticket, const string symbol, const long magic,
                       S1TrailConfig &cfg)
{
   if(!cfg.trailing_enabled && !cfg.breakeven_enabled)
      return;
   if(!PositionSelectByTicket(ticket))
      return;
   if(PositionGetString(POSITION_SYMBOL) != symbol)
      return;
   if((long)PositionGetInteger(POSITION_MAGIC) != magic)
      return;

   const long pos_type = PositionGetInteger(POSITION_TYPE);
   const double price_open = PositionGetDouble(POSITION_PRICE_OPEN);
   const double sl = PositionGetDouble(POSITION_SL);
   const double tp = PositionGetDouble(POSITION_TP);

   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick))
      return;

   const double current_price = (pos_type == POSITION_TYPE_BUY) ? tick.bid : tick.ask;
   const double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   const double pip_size = S1_PipSizeManage(symbol);

   double profit_points = 0.0;
   double profit_pips = 0.0;
   if(pos_type == POSITION_TYPE_BUY)
   {
      profit_points = (current_price - price_open) / point;
      profit_pips = (current_price - price_open) / pip_size;
   }
   else
   {
      profit_points = (price_open - current_price) / point;
      profit_pips = (price_open - current_price) / pip_size;
   }

   double sl_distance_from_entry = 0.0;
   if(pos_type == POSITION_TYPE_BUY)
      sl_distance_from_entry = (sl > 0.0) ? (price_open - sl) / pip_size : 0.0;
   else
      sl_distance_from_entry = (sl > 0.0) ? (sl - price_open) / pip_size : 0.0;

   double initial_sl_distance_pips = 100.0;
   if(sl_distance_from_entry >= 5.0)
      initial_sl_distance_pips = MathMax(sl_distance_from_entry, 50.0);

   double new_sl = sl;
   bool modify = false;

   if(cfg.breakeven_enabled)
   {
      double breakeven_trigger_pips_calc = 30.0;
      if(S1_IsAutoPips(cfg.breakeven_trigger_pips))
         breakeven_trigger_pips_calc = initial_sl_distance_pips * cfg.breakeven_trigger_percent;
      else
      {
         const double fixed = StringToDouble(cfg.breakeven_trigger_pips);
         breakeven_trigger_pips_calc = MathMax(fixed, initial_sl_distance_pips * cfg.breakeven_trigger_percent);
      }

      const double breakeven_trigger_points = breakeven_trigger_pips_calc * pip_size / point;
      if(profit_points > breakeven_trigger_points)
      {
         bool is_breakeven = false;
         if(pos_type == POSITION_TYPE_BUY)
            is_breakeven = (sl >= price_open);
         else
            is_breakeven = (sl > 0.0 && sl <= price_open);

         if(!is_breakeven)
         {
            new_sl = price_open;
            modify = true;
            PrintFormat("Moved SL to Breakeven ticket=%I64u profit=%.1f pips trigger=%.1f",
                        ticket, profit_pips, breakeven_trigger_pips_calc);
         }
      }
   }

   if(cfg.trailing_enabled && !modify)
   {
      double trailing_trigger_pips_calc = 50.0;
      if(S1_IsAutoPips(cfg.trailing_trigger_pips))
         trailing_trigger_pips_calc = initial_sl_distance_pips * cfg.trailing_trigger_multiplier;
      else
      {
         const double fixed = StringToDouble(cfg.trailing_trigger_pips);
         trailing_trigger_pips_calc = MathMax(fixed, initial_sl_distance_pips * cfg.trailing_trigger_multiplier);
      }

      const double trailing_trigger_points = trailing_trigger_pips_calc * pip_size / point;
      if(profit_points > trailing_trigger_points)
      {
         double trail_dist = cfg.trailing_distance_pips * pip_size;
         if(S1_StringEqualsIgnoreCase(cfg.trailing_mode, "atr"))
         {
            ENUM_TIMEFRAMES atr_tf = PERIOD_M5;
            if(S1_StringEqualsIgnoreCase(cfg.trailing_atr_timeframe, "M1"))
               atr_tf = PERIOD_M1;
            else if(S1_StringEqualsIgnoreCase(cfg.trailing_atr_timeframe, "M15"))
               atr_tf = PERIOD_M15;

            MqlRates atr_rates[];
            int atr_copied = 0;
            if(S1_CopyRatesChrono(symbol, atr_tf, 50, atr_rates, atr_copied) && atr_copied > 14)
            {
               double high_a[], low_a[], close_a[];
               ArrayResize(high_a, atr_copied);
               ArrayResize(low_a, atr_copied);
               ArrayResize(close_a, atr_copied);
               for(int i = 0; i < atr_copied; i++)
               {
                  high_a[i] = atr_rates[i].high;
                  low_a[i] = atr_rates[i].low;
                  close_a[i] = atr_rates[i].close;
               }
               const double atr_value = S1_CalcATR(high_a, low_a, close_a, atr_copied, 14, 0);
               if(atr_value > 0.0)
               {
                  double trail_dist_pips = (atr_value * cfg.trailing_atr_multiplier) / pip_size;
                  trail_dist_pips = MathMax(cfg.trailing_min_pips, MathMin(trail_dist_pips, cfg.trailing_max_pips));
                  trail_dist = trail_dist_pips * pip_size;
               }
            }
         }

         if(pos_type == POSITION_TYPE_BUY)
         {
            const double candidate = current_price - trail_dist;
            if(candidate > sl)
            {
               new_sl = candidate;
               modify = true;
            }
         }
         else
         {
            const double candidate = current_price + trail_dist;
            if(sl == 0.0 || candidate < sl)
            {
               new_sl = candidate;
               modify = true;
            }
         }

         if(modify)
            PrintFormat("Trailing SL ticket=%I64u %.2f -> %.2f profit=%.1f pips",
                        ticket, sl, new_sl, profit_pips);
      }
   }

   if(modify)
   {
      MqlTradeRequest req = {};
      MqlTradeResult  res = {};
      req.action   = TRADE_ACTION_SLTP;
      req.position = ticket;
      req.symbol   = symbol;
      req.sl       = NormalizeDouble(new_sl, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
      req.tp       = tp;
      req.magic    = magic;
      if(!OrderSend(req, res))
         PrintFormat("Failed to update SL/TP ticket=%I64u err=%d", ticket, GetLastError());
   }
}

int S1_CancelPendingOrders(const string symbol, const long magic, const bool account_scope)
{
   int removed = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      const ulong ticket = OrderGetTicket(i);
      if(ticket == 0 || !OrderSelect(ticket))
         continue;
      if(!account_scope)
      {
         if(OrderGetString(ORDER_SYMBOL) != symbol)
            continue;
         if((long)OrderGetInteger(ORDER_MAGIC) != magic)
            continue;
      }

      MqlTradeRequest req = {};
      MqlTradeResult  res = {};
      req.action = TRADE_ACTION_REMOVE;
      req.order  = ticket;
      if(OrderSend(req, res))
         removed++;
   }
   return removed;
}

int S1_ClosePositions(const string symbol, const long magic, const bool account_scope)
{
   CTrade trade;
   trade.SetExpertMagicNumber(magic);
   int closed = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(!account_scope)
      {
         if(PositionGetString(POSITION_SYMBOL) != symbol)
            continue;
         if((long)PositionGetInteger(POSITION_MAGIC) != magic)
            continue;
      }

      if(trade.PositionClose(ticket))
         closed++;
   }
   return closed;
}

string S1_WeekendStateFileName(const long account)
{
   return StringFormat("ha_weekend_flatten_%I64d.json", account);
}

bool S1_WeekendFlattenLoadState(const long account, string &friday_key, bool &completed)
{
   friday_key = "";
   completed = false;
   const string fname = S1_WeekendStateFileName(account);
   int handle = FileOpen(fname, FILE_READ | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
      return false;

   string content = "";
   while(!FileIsEnding(handle))
      content += FileReadString(handle);
   FileClose(handle);

   int pos = StringFind(content, "\"friday_utc_date\"");
   if(pos >= 0)
   {
      int q1 = StringFind(content, "\"", pos + 18);
      int q2 = StringFind(content, "\"", q1 + 1);
      if(q1 >= 0 && q2 > q1)
         friday_key = StringSubstr(content, q1 + 1, q2 - q1 - 1);
   }
   completed = (StringFind(content, "\"completed\": true") >= 0 || StringFind(content, "\"completed\":true") >= 0);
   return true;
}

void S1_WeekendFlattenSaveState(const long account, const string friday_key)
{
   const string fname = S1_WeekendStateFileName(account);
   int handle = FileOpen(fname, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
      return;

   FileWriteString(handle, StringFormat(
      "{\r\n  \"friday_utc_date\": \"%s\",\r\n  \"completed\": true,\r\n  \"ts_utc\": \"%s\"\r\n}",
      friday_key, TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS)));
   FileClose(handle);
}

bool S1_WeekendFlattenMaybe(const string symbol, const long magic, const double root_volume,
                            const bool enabled, const string scope,
                            const int close_utc_hour, const int close_utc_minute,
                            const int minutes_before, const double weekend_volume,
                            const bool has_weekend_volume,
                            const string direction, const string comment,
                            const int deviation, const double sl, const double tp,
                            bool &should_shutdown)
{
   should_shutdown = false;
   if(!enabled || symbol == "")
      return false;

   datetime now_gmt = TimeGMT();
   MqlDateTime dt;
   TimeToStruct(now_gmt, dt);
   if(dt.day_of_week != 5)
      return false;

   const int mb = MathMax(1, minutes_before);
   MqlDateTime close_begin_dt = dt;
   close_begin_dt.hour = close_utc_hour;
   close_begin_dt.min = close_utc_minute;
   close_begin_dt.sec = 0;
   const datetime close_begin = StructToTime(close_begin_dt);
   const datetime window_start = close_begin - mb * 60;
   const datetime close_end = close_begin + 59;

   if(now_gmt < window_start || now_gmt > close_end)
      return false;

   string friday_key = StringFormat("%04d-%02d-%02d", dt.year, dt.mon, dt.day);
   string saved_key;
   bool completed = false;
   S1_WeekendFlattenLoadState((long)AccountInfoInteger(ACCOUNT_LOGIN), saved_key, completed);
   if(saved_key == friday_key && completed)
      return false;

   double vol = root_volume;
   if(has_weekend_volume && weekend_volume > 0.0)
      vol = weekend_volume;

   string scope_l = scope;
   StringTrimLeft(scope_l);
   StringTrimRight(scope_l);
   StringToLower(scope_l);
   const bool account_scope = (scope_l == "account");
   PrintFormat("[HA weekend] Friday UTC %02d:%02d scope=%s market %s %s vol=%.2f",
               dt.hour, dt.min, scope, direction, symbol, vol);

   const int n_rm = S1_CancelPendingOrders(symbol, magic, account_scope);
   const int n_cl = S1_ClosePositions(symbol, magic, account_scope);
   PrintFormat("[HA weekend] Cancelled %d pending, closed %d positions", n_rm, n_cl);

   string dir = direction;
   StringToUpper(dir);
   if(dir == "BUY" || dir == "SELL")
   {
      CTrade trade;
      trade.SetExpertMagicNumber(magic);
      trade.SetDeviationInPoints(deviation);
      trade.SetTypeFilling(S1_GetFillingMode(symbol));

      bool ok = false;
      if(dir == "BUY")
         ok = trade.Buy(vol, symbol, 0.0, sl, tp, comment);
      else
         ok = trade.Sell(vol, symbol, 0.0, sl, tp, comment);

      if(ok)
         PrintFormat("[HA weekend] Market %s OK", dir);
      else
         PrintFormat("[HA weekend] Market %s failed retcode=%d", dir, trade.ResultRetcode());
   }

   S1_WeekendFlattenSaveState((long)AccountInfoInteger(ACCOUNT_LOGIN), friday_key);
   should_shutdown = true;
   return true;
}

#endif
