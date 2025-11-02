#!/bin/bash

# Script chạy Gold Auto Trader
# Sử dụng: ./run_gold_trader.sh

echo "🥇 Gold Auto Trader - Bắt đầu chạy bot..."
echo ""

# Kiểm tra thư mục logs
if [ ! -d "logs" ]; then
    mkdir -p logs
    echo "✅ Đã tạo thư mục logs"
fi

# Chạy bot
cd examples
python3 gold_auto_trader.py

