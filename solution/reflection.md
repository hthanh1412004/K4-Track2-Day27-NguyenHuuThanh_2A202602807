# Thu hoạch Data Siege

**Học viên:** Nguyễn Hữu Thành — 2A202602807 — K4, Track 2, Day 27.

**Loại lỗi khó phát hiện nhất.** Các lỗi phân phối và drift có độ lệch nhỏ khó
hơn lỗi cấu trúc: thiếu upstream hay vi phạm schema có bằng chứng trực tiếp,
còn các chỉ số thống kê có thể nằm gần vùng dao động tự nhiên. Với data batch,
em kết hợp kiểm tra từng chỉ số với khoảng cách đa chiều, chuẩn hóa volume và
mean amount theo nửa khoảng baseline 3σ, rồi kết hợp null rate và độ trễ.
Ngưỡng khoảng cách là 1,30. Với feature drift, em dùng ngưỡng 0,65σ theo
GUIDE.md để tránh báo nhầm dao động sạch vượt baseline lịch sử 0,4095σ.
Embedding dùng ngưỡng dịch chuyển 0,040 và tuổi tài liệu 45 ngày theo khoảng
phân tách trong hướng dẫn.

**Đánh đổi chi phí và độ bao phủ.** Mỗi sự kiện gọi đúng một công cụ tương ứng,
không gọi lặp hay bỏ kiểm tra khi hết ngân sách. Metadata hiện có không đủ để
kết luận các phép đo sâu là bình thường. Public dùng 240/220 credits, chịu phạt
khoảng 1,82 điểm; chấp nhận khoản này giúp duy trì độ bao phủ. Khi công cụ trả
về `error`, handler không suy diễn thành lỗi dữ liệu và ghi bộ đếm vào
`ctx.state`; vì vậy lỗi đo lường vẫn là một giới hạn cần theo dõi.

**Kết quả kiểm thử.** Selfcheck đạt đủ 5 handler. Practice đạt 50,00 điểm,
TP=33, FP=0, FN=0, TN=87, dùng 180/220 credits. Public đạt 46,90 điểm,
TPR=0,9744, FPR=0, cả bốn pillar đều `high`. Private chạy một lượt với nguyên
logic đã kiểm thử, đạt 32,41 điểm, TPR=0,6481, FPR=0, không vượt ngân sách.
Kết quả cho thấy giữ được mức báo động giả thấp nhưng còn bỏ sót nhiều lỗi
tinh vi; đạt tối đa Practice chưa bảo đảm tổng quát hóa tốt. Báo cáo được giữ
nguyên từ harness, không chỉnh sửa hoặc dò đáp án Private.

**Nếu có thêm thời gian.** Em sẽ lưu cửa sổ thống kê theo bảng, feature view và
corpus trong `ctx.state`, dùng median/MAD chống nhiễu và EWMA để nhận biết
dịch chuyển kéo dài. Cần có giai đoạn khởi động và tránh cập nhật baseline bằng
các mẫu đã cảnh báo để hạn chế nhiễm lỗi. Ngưỡng thích nghi phải được đánh giá
trên nhiều luồng sạch và luồng lỗi độc lập, đo cả TPR, FPR và chi phí, thay vì
điều chỉnh theo điểm của một lượt Private.
