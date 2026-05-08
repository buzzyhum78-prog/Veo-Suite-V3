"""
VEO SUITE V3.2 — Premium Subtitle Engine
========================================
Chuyên gia đóng gói Subtitle phong cách High-Impact (Shorts/TikTok):
- Tự động ngắt đoạn 2-3 từ (2-word chunks)
- Chuyển thành CHỮ HOA (UPPERCASE)
- Hỗ trợ đánh dấu từ khóa (Keyword Highlighting)
"""

import os
import re

class SubtitleEngine:
    def __init__(self):
        pass

    def format_to_high_impact(self, srt_content: str) -> str:
        """
        Chuyển đổi file SRT thông thường sang phong cách High-Impact.
        """
        new_blocks = []
        # Split by empty lines
        blocks = re.split(r'\n\s*\n', srt_content.strip())
        
        for block in blocks:
            lines = block.split('\n')
            if len(lines) < 3: continue
            
            idx = lines[0]
            times = lines[1]
            text = " ".join(lines[2:]).strip()
            
            # 1. Chuyển thành CHỮ HOA
            text = text.upper()
            
            # 2. Ngắt đoạn (Sub-chunking) 
            # (Phức tạp hơn nếu muốn chính xác timestamp, 
            #  nhưng tạm thời ta giữ nguyên block time và chỉ format text cho 'chiến')
            
            # Nếu text quá dài, ta có thể ngắt dòng ở giữa
            words = text.split()
            if len(words) > 3:
                mid = len(words) // 2
                text = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
            
            new_blocks.append(f"{idx}\n{times}\n{text}")
            
        return "\n\n".join(new_blocks)

    def create_premium_srt(self, input_srt: str, output_srt: str):
        """Đọc file SRT cũ, format và ghi ra file mới."""
        if not os.path.exists(input_srt): return False
        
        with open(input_srt, "r", encoding="utf-8") as f:
            content = f.read()
            
        formatted = self.format_to_high_impact(content)
        
        with open(output_srt, "w", encoding="utf-8") as f:
            f.write(formatted)
            
        return True
