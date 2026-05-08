
# Bản đồ Giờ Vàng (Golden Hours) theo Quốc gia (Giờ địa phương)
# Dữ liệu dựa trên báo cáo hành động người dùng đa nền tảng (YouTube, TikTok, Facebook)
GOLDEN_HOURS = {
    "Hoa Kỳ": ["18:00", "20:00", "21:30"],
    "Mỹ": ["18:00", "20:00", "21:30"],
    "US": ["18:00", "20:00", "21:30"],
    "Việt Nam": ["11:30", "20:00", "22:00"],
    "VN": ["11:30", "20:00", "22:00"],
    "Nhật Bản": ["07:30", "19:00", "21:00"],
    "JP": ["07:30", "19:00", "21:00"],
    "Hàn Quốc": ["08:00", "18:30", "22:00"],
    "KR": ["08:00", "18:30", "22:00"],
    "Anh": ["17:00", "19:00", "21:00"],
    "UK": ["17:00", "19:00", "21:00"],
    "Đức": ["18:00", "20:30"],
    "DE": ["18:00", "20:30"],
    "Pháp": ["19:00", "21:00"],
    "FR": ["19:00", "21:00"],
    "Brazil": ["10:00", "18:00", "20:00"],
    "BR": ["10:00", "18:00", "20:00"],
    "Global": ["12:00", "18:00", "21:00"]
}

def get_next_golden_hour(country_name):
    """Tính toán giờ vàng tiếp theo dựa trên quốc gia"""
    import datetime
    hours = GOLDEN_HOURS.get(country_name, GOLDEN_HOURS["Global"])
    
    now = datetime.datetime.now()
    # Logic đơn giản: Lấy giờ vàng đầu tiên trong danh sách mà chưa trôi qua trong ngày
    # Nếu trôi qua hết rồi thì lấy giờ vàng đầu tiên của ngày mai
    for h_str in hours:
        h, m = map(int, h_str.split(':'))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target > now:
            return target
            
    # Nếu không tìm thấy giờ nào lớn hơn bây giờ -> Lấy giờ đầu tiên của ngày mai
    h, m = map(int, hours[0].split(':'))
    return (now + datetime.timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
