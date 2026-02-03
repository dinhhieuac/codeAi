1\. ATR\_current / ATR\_avg(20) ∈ \[0.8 ; 1.6\]   	(lọc lịm \+ news ☺)

	Nếu ATR ratio ∉ \[0.8 ; 1.6\]

	→ KHÔNG xét Delta

	→ Count \= 0

2\. Delta hợp lệ:

**DeltaHigh \= High\[i\] \- High\[i-1\]**

**DeltaLow \= Low\[i-1\] \- Low\[i\]**

**SELL:**

DeltaHigh \= High\[i\] \- High\[i-1\]

Nếu

	DeltaHigh \> 0

	Và DeltaHigh \< k\*ATR

	Và DeltaLow ≤ 0 (khoá hướng) 

	🡪 Count \= Count \+ 1

Ngược lại 

	Count \= 0

**BUY:**

DeltaLow \= Low\[i-1\] \- Low\[i\]

Nếu

	DeltaLow \> 0

	Và DeltaLow \< k\*ATR

	Và DeltaHigh ≤ 0 (khoá hướng) 

	🡪 Count \= Count \+ 1

Ngược lại

 	Count \= 0

| Market | k |
| :---- | :---- |
| Forex | 0.3 |
| Gold | 0.33 |
| BTC | 0.48 |

3\. Range filter áp dụng cho NẾN DELTA HỢP LỆ

Range ≥  q \* ATR      (có mở biên)

Range \= High – Low

Nếu Range \< q\*ATR → Count \= 0

| Market | q |
| :---- | :---- |
| Forex | 0.55 |
| Gold | 0.65 |
| BTC | 0.7 |

4\. Count \= 2  **(liên tiếp 2 nến)** \- Entry tại giá đóng cửa của nến delta hợp lệ \= 2

5\. SL \= 2ATR    TP \= 2SL , dời SL về entry khi có lãi, sau đó dời SL theo E\*ATR.

**Công thức 1** – **BUY**

* Nếu lợi nhuận hiện tại ≥ E\*ATR  
  **→** dời Stop Loss về Entry  
* Nếu lợi nhuận ≥ mức bắt đầu trailing (0.5\*ATR)  
  **→** bắt đầu dời SL theo biến động thị trường  
* SL mới \= đỉnh cao nhất kể từ khi vào lệnh − 0.5 × ATR

	SL \= max(SL, HighestHigh \- 0.5 \* ATR)

	Chỉ cho phép SL đi lên, không bao giờ đi xuống

	

**Công thức 2 –** **SELL**

* Nếu lợi nhuận ≥ E\*ATR  
  **→** dời Stop Loss về Entry  
* Nếu lợi nhuận ≥ mức bắt đầu trailing (0.5\*ATR)  
  **→** bắt đầu dời SL theo biến động thị trường  
* SL mới \= đáy thấp nhất kể từ khi vào lệnh \+ 0.5 × ATR

	SL \= min(SL, LowestLow \+ 0.5 \* ATR)

	SL chỉ được hạ xuống, không bao giờ kéo lên

| Market | E |
| :---- | :---- |
| Forex | 0.3 |
| Gold | 0.35 |
| BTC | 0.4 |

6\. Cooldown: 3 phút/Symbol

Cooldown bắt đầu tính từ thời điểm đóng lệnh