# Grid Step Trading Bot -- Strategy Idea

## 1. Overview

This trading bot uses a **price grid / step strategy** without relying
on traditional technical indicators.

The bot continuously places **two pending orders around the current
market price**:

-   A BUY STOP above the price
-   A SELL STOP below the price

When one order is triggered, the bot **shifts the grid in that
direction** and places a new pair of pending orders.

This approach attempts to capture **market movement step‑by‑step**,
especially during trends.

------------------------------------------------------------------------

# 2. Basic Example

Assume:

Current Price = 5000\
Grid Step = 5

The bot places:

BUY STOP = 5005\
SELL STOP = 4995

------------------------------------------------------------------------

# 3. If BUY 5005 is Triggered

The grid shifts upward.

New orders:

BUY STOP = 5010\
SELL STOP = 5000

This allows the bot to **follow an upward trend**.

Example:

5000\
→ BUY 5005 triggered\
→ BUY 5010 triggered\
→ BUY 5015 triggered

The bot captures multiple steps of the trend.

------------------------------------------------------------------------

# 4. If SELL 4995 is Triggered

The grid shifts downward.

New orders:

BUY STOP = 5000\
SELL STOP = 4990

Example:

5000\
→ SELL 4995 triggered\
→ SELL 4990 triggered\
→ SELL 4985 triggered

The bot follows the downward movement.

------------------------------------------------------------------------

# 5. Core Bot Logic

Pseudo code:

    step = 5

    current_price = get_price()

    place_buy_stop(current_price + step)
    place_sell_stop(current_price - step)

    on_buy_filled(price):

        cancel_previous_pending()

        place_buy_stop(price + step)
        place_sell_stop(price - step)

    on_sell_filled(price):

        cancel_previous_pending()

        place_buy_stop(price + step)
        place_sell_stop(price - step)

------------------------------------------------------------------------

# 6. Prevent Opening Too Many Orders

The bot must avoid placing multiple trades within the same price range.

### Grid Zone Lock

Each grid level can only contain **one order**.

Example grid levels:

4995\
5000\
5005\
5010

If a trade already exists at **5005**, the bot will not open another
one.

------------------------------------------------------------------------

### Distance Filter

Minimum distance between positions:

    min_distance = 5

If a new order is too close to an existing order, it is skipped.

------------------------------------------------------------------------

### Max Positions

Limit total open trades.

Example:

    max_positions = 5

This prevents runaway exposure.

------------------------------------------------------------------------

# 7. Risk Management

Important protection rules:

### Basket Take Profit

Close all trades when total profit reaches target.

Example:

    profit >= target_profit
    close_all_positions()
    reset_grid()

------------------------------------------------------------------------

### Spread Protection

Grid size must be larger than spread.

Example (Gold):

Spread ≈ 3--5 points\
Recommended Grid ≥ 10 points

------------------------------------------------------------------------

# 8. Advantages

-   Simple logic
-   No indicators required
-   Easy to automate
-   Works well in trending markets

------------------------------------------------------------------------

# 9. Risks

### Sideways Market

Price moves up and down repeatedly:

5005 BUY\
5000 SELL\
5005 BUY\
5000 SELL

This causes **whipsaw losses**.

------------------------------------------------------------------------

### News Volatility

Large spikes can trigger multiple orders quickly.

------------------------------------------------------------------------

### Trend Reversal

Example:

BUY 5005\
BUY 5010\
BUY 5015

Then market drops to 4970.

This creates a **drawdown on the long positions**.

------------------------------------------------------------------------

# 10. Possible Improvements

Professional grid bots often add:

-   Volatility filters
-   Time filters (avoid news)
-   Trend bias
-   Multi‑layer grids

Example:

Micro Grid = 5 points\
Macro Grid = 30 points\
Super Grid = 100 points

------------------------------------------------------------------------

# 11. Summary

This bot is based on a **step-following grid system**.

Main idea:

1.  Place buy and sell pending orders around price
2.  When one triggers, shift the grid
3.  Follow market movement step by step
4.  Apply strict position and risk limits

With proper risk management, this strategy can be used to build
**automated trading systems**.
