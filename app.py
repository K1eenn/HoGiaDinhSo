import streamlit as st
from openai import OpenAI
import dotenv
import os
from PIL import Image
from audio_recorder_streamlit import audio_recorder
import base64
from io import BytesIO
import json
import datetime
import random
import hashlib
import requests
import time

dotenv.load_dotenv()

# Đường dẫn file lưu trữ dữ liệu
FAMILY_DATA_FILE = "family_data.json"
EVENTS_DATA_FILE = "events_data.json"
NOTES_DATA_FILE = "notes_data.json"
CHAT_HISTORY_FILE = "chat_history.json"

# Thiết lập log để debug
import logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   handlers=[logging.StreamHandler()])
logger = logging.getLogger('family_assistant')

# Chỉ sử dụng một mô hình duy nhất
openai_model = "gpt-4o-mini"

# ------ TAVILY API INTEGRATION ------
def tavily_extract(api_key, urls, include_images=False, extract_depth="basic"):
    """
    Trích xuất nội dung từ URL sử dụng Tavily Extract API
    
    Args:
        api_key (str): Tavily API Key
        urls (str/list): URL hoặc danh sách URL cần trích xuất
        include_images (bool): Có bao gồm hình ảnh hay không
        extract_depth (str): Độ sâu trích xuất ('basic' hoặc 'advanced')
        
    Returns:
        dict: Kết quả trích xuất hoặc None nếu có lỗi
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "urls": urls,
        "include_images": include_images,
        "extract_depth": extract_depth
    }
    
    try:
        response = requests.post(
            "https://api.tavily.com/extract",
            headers=headers,
            json=data
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Lỗi Tavily Extract: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Lỗi khi gọi Tavily API: {e}")
        return None

def tavily_search(api_key, query, search_depth="advanced", max_results=3, include_domains=None, exclude_domains=None):
    """
    Thực hiện tìm kiếm thời gian thực sử dụng Tavily Search API
    
    Args:
        api_key (str): Tavily API Key
        query (str): Câu truy vấn tìm kiếm
        search_depth (str): Độ sâu tìm kiếm ('basic' hoặc 'advanced')
        max_results (int): Số lượng kết quả tối đa
        include_domains (list): Danh sách domain muốn bao gồm
        exclude_domains (list): Danh sách domain muốn loại trừ
        
    Returns:
        dict: Kết quả tìm kiếm hoặc None nếu có lỗi
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results
    }
    
    if include_domains:
        data["include_domains"] = include_domains
    
    if exclude_domains:
        data["exclude_domains"] = exclude_domains
    
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            headers=headers,
            json=data
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Lỗi Tavily Search: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Lỗi khi gọi Tavily Search API: {e}")
        return None

def search_and_summarize(tavily_api_key, query, openai_api_key, time_info=""):
    """
    Tìm kiếm và tổng hợp thông tin từ kết quả tìm kiếm, đảm bảo tập trung vào thời gian cụ thể
    
    Args:
        tavily_api_key (str): Tavily API Key
        query (str): Câu truy vấn tìm kiếm
        openai_api_key (str): OpenAI API Key
        time_info (str): Thông tin thời gian cụ thể từ câu hỏi
        
    Returns:
        str: Thông tin đã được tổng hợp
    """
    if not tavily_api_key or not openai_api_key or not query:
        return "Thiếu thông tin để thực hiện tìm kiếm hoặc tổng hợp."
    
    try:
        # Điều chỉnh query để tập trung vào thời gian cụ thể
        search_query = query
        if time_info:
            # Thêm thông tin thời gian vào truy vấn nếu chưa có
            if time_info.lower() not in query.lower():
                search_query = f"{query} {time_info}"
            
            logger.info(f"Đã điều chỉnh truy vấn tìm kiếm với thông tin thời gian: '{search_query}'")
        
        # Thực hiện tìm kiếm với Tavily
        search_results = tavily_search(tavily_api_key, search_query)
        
        if not search_results or "results" not in search_results:
            return "Không tìm thấy kết quả nào."
        
        # Trích xuất thông tin từ top kết quả
        urls_to_extract = [result["url"] for result in search_results["results"][:3]]
        extracted_contents = []
        
        for url in urls_to_extract:
            extract_result = tavily_extract(tavily_api_key, url)
            if extract_result and "results" in extract_result and len(extract_result["results"]) > 0:
                content = extract_result["results"][0].get("raw_content", "")
                # Giới hạn độ dài nội dung để tránh token quá nhiều
                if len(content) > 8000:
                    content = content[:8000] + "..."
                extracted_contents.append({
                    "url": url,
                    "content": content
                })
        
        if not extracted_contents:
            return "Không thể trích xuất nội dung từ các kết quả tìm kiếm."
        
        # Tổng hợp thông tin sử dụng OpenAI
        client = OpenAI(api_key=openai_api_key)
        
        # Chuẩn bị prompt cho việc tổng hợp, nhấn mạnh yêu cầu về thời gian
        time_instruction = ""
        if time_info:
            time_instruction = f"""
            QUAN TRỌNG: Người dùng đang tìm kiếm thông tin liên quan đến "{time_info}". 
            Hãy tập trung vào tin tức và sự kiện xảy ra trong khoảng thời gian này.
            Nếu không tìm thấy thông tin phù hợp với thời gian này, hãy nói rõ rằng không có thông tin cho thời điểm cụ thể này.
            """
        
        prompt = f"""
        Dưới đây là các nội dung trích xuất từ internet liên quan đến câu hỏi: "{query}"
        
        {json.dumps(extracted_contents, ensure_ascii=False)}
        
        {time_instruction}
        
        Hãy tổng hợp thông tin từ các nguồn trên để trả lời câu hỏi một cách đầy đủ và chính xác.
        Hãy trình bày thông tin một cách rõ ràng, có cấu trúc.
        Nếu thông tin từ các nguồn khác nhau mâu thuẫn, hãy đề cập đến điều đó.
        Hãy ghi rõ nguồn thông tin (URL) ở cuối mỗi phần thông tin.
        
        Nếu có thông tin về ngày đăng hoặc thời gian của tin tức, hãy ghi rõ để người dùng biết thông tin là mới nhất.
        """
        
        response = client.chat.completions.create(
            model=openai_model,
            messages=[
                {"role": "system", "content": "Bạn là trợ lý tổng hợp thông tin. Nhiệm vụ của bạn là tổng hợp thông tin từ nhiều nguồn để cung cấp câu trả lời đầy đủ, chính xác và có cấu trúc. Bạn cần đảm bảo rằng thông tin phù hợp với thời gian mà người dùng yêu cầu."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        
        summarized_info = response.choices[0].message.content
        
        # Thêm thông báo về nguồn
        sources_info = "\n\n**Nguồn thông tin:**\n" + "\n".join([f"- {result['url']}" for result in search_results["results"][:3]])
        
        return f"{summarized_info}\n{sources_info}"
    
    except Exception as e:
        logger.error(f"Lỗi trong quá trình tìm kiếm và tổng hợp: {e}")
        return f"Có lỗi xảy ra trong quá trình tìm kiếm và tổng hợp thông tin: {str(e)}"

# Thêm hàm tạo câu hỏi gợi ý động
def generate_dynamic_suggested_questions(api_key, member_id=None, max_questions=5):
    """
    Tạo câu hỏi gợi ý cá nhân hóa và linh động dựa trên thông tin thành viên, 
    lịch sử trò chuyện và thời điểm hiện tại
    """
    # Kiểm tra cache để tránh tạo câu hỏi mới quá thường xuyên
    cache_key = f"suggested_questions_{member_id}_{datetime.datetime.now().strftime('%Y-%m-%d_%H')}"
    if "question_cache" in st.session_state and cache_key in st.session_state.question_cache:
        return st.session_state.question_cache[cache_key]
    
    # Xác định trạng thái người dùng hiện tại
    member_info = {}
    if member_id and member_id in family_data:
        member = family_data[member_id]
        member_info = {
            "name": member.get("name", ""),
            "age": member.get("age", ""),
            "preferences": member.get("preferences", {})
        }
    
    # Thu thập dữ liệu về các sự kiện sắp tới
    upcoming_events = []
    today = datetime.datetime.now().date()
    
    for event_id, event in events_data.items():
        try:
            event_date = datetime.datetime.strptime(event.get("date", ""), "%Y-%m-%d").date()
            if event_date >= today:
                date_diff = (event_date - today).days
                if date_diff <= 14:  # Chỉ quan tâm sự kiện trong 2 tuần tới
                    upcoming_events.append({
                        "title": event.get("title", ""),
                        "date": event.get("date", ""),
                        "days_away": date_diff
                    })
        except Exception as e:
            logger.error(f"Lỗi khi xử lý ngày sự kiện: {e}")
            continue
    
    # Lấy dữ liệu về chủ đề từ lịch sử trò chuyện gần đây
    recent_topics = []
    if member_id and member_id in chat_history and chat_history[member_id]:
        # Lấy tối đa 3 cuộc trò chuyện gần nhất
        recent_chats = chat_history[member_id][:3]
        
        for chat in recent_chats:
            summary = chat.get("summary", "")
            if summary:
                recent_topics.append(summary)
    
    questions = []
    
    # Phương thức 1: Sử dụng OpenAI API để sinh câu hỏi thông minh nếu có API key
    if api_key and api_key.startswith("sk-"):
        try:
            # Tạo nội dung prompt cho OpenAI
            context = {
                "member": member_info,
                "upcoming_events": upcoming_events,
                "recent_topics": recent_topics,
                "current_time": datetime.datetime.now().strftime("%H:%M"),
                "current_day": datetime.datetime.now().strftime("%A"),
                "current_date": datetime.datetime.now().strftime("%Y-%m-%d")
            }
            
            prompt = f"""
            Hãy tạo {max_questions} câu gợi ý đa dạng và cá nhân hóa cho người dùng trợ lý gia đình dựa trên thông tin sau:
            
            Thông tin người dùng: {json.dumps(member_info, ensure_ascii=False)}
                        
            
            Yêu cầu:
            1. Mỗi câu gợi ý nên tập trung vào MỘT sở thích cụ thể, không kết hợp nhiều sở thích
            2. KHÔNG kết thúc câu gợi ý bằng bất kỳ cụm từ nào như "bạn có biết không?", "bạn có muốn không?", v.v.
            3. Đưa ra thông tin cụ thể, chi tiết và chính xác như thể bạn đang viết một bài đăng trên mạng xã hội
            4. Mục đích là cung cấp thông tin hữu ích, không phải bắt đầu cuộc trò chuyện
            5. Chỉ trả về danh sách các câu gợi ý, mỗi câu trên một dòng
            6. Không thêm đánh số hoặc dấu gạch đầu dòng
            
            Ví dụ tốt:
            - "Top 5 phim hành động hay nhất 2023?"
            - "Công thức bánh mì nguyên cám giảm cân?"
            - "Kết quả Champions League?"
            - "5 bài tập cardio giảm mỡ bụng hiệu quả?"
            
            Ví dụ không tốt:
            - "Bạn đã biết bộ phim 'The Goal' vừa được phát hành và nhận nhiều phản hồi tích cực từ khán giả chưa?" (Kết hợp phim + bóng đá)
            - "Kết quả trận đấu Champions League: Man City 3-1 Real Madrid, bạn có theo dõi không?" (Kết thúc bằng câu hỏi)
            - "Bạn có muốn xem những phát hiện mới về dinh dưỡng không?" (Không cung cấp thông tin cụ thể)
            
            Trả về chính xác {max_questions} câu gợi ý.
            """
            
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=openai_model,
                messages=[
                    {"role": "system", "content": "Bạn là trợ lý tạo câu hỏi gợi ý cá nhân hóa."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=300
            )
            
            # Xử lý phản hồi từ OpenAI
            generated_content = response.choices[0].message.content.strip()
            questions = [q.strip() for q in generated_content.split('\n') if q.strip()]
            
            # Lấy số lượng câu hỏi theo yêu cầu
            questions = questions[:max_questions]
            
            logger.info(f"Đã tạo {len(questions)} câu hỏi gợi ý bằng OpenAI API")
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo câu hỏi với OpenAI: {e}")
            # Tiếp tục với phương thức 2 (dự phòng)
    
            # Phương thức 2: Dùng mẫu câu + thông tin cá nhân nếu không thể sử dụng OpenAI API
    if not questions:
        logger.info("Sử dụng phương pháp mẫu câu để tạo câu hỏi gợi ý")
        
        # Tạo seed dựa trên ngày và ID thành viên để tạo sự đa dạng
        random_seed = int(hashlib.md5(f"{datetime.datetime.now().strftime('%Y-%m-%d_%H')}_{member_id or 'guest'}".encode()).hexdigest(), 16) % 10000
        random.seed(random_seed)
        
        # Mẫu câu thông tin cụ thể theo nhiều chủ đề khác nhau (không có câu hỏi cuối câu)
        question_templates = {
            "food": [
                "Top 10 món {food} ngon nhất Việt Nam?",
                "Công thức làm món {food} ngon tại nhà?",
                "5 biến tấu món {food} cho bữa {meal}?",
                "Bí quyết làm món {food} ngon như nhà hàng 5 sao?",
                "Cách làm món {food} chuẩn vị {season}?",
                "3 cách chế biến món {food} giảm 50% calo?"
            ],
            "movies": [
                "Top 5 phim chiếu rạp tuần này: {movie1}, {movie2}, {movie3} - Đặt vé ngay để nhận ưu đãi.",
                "Phim mới ra mắt {movie1}?",
                "Đánh giá phim {movie1}?",
                "{actor} vừa giành giải Oscar cho vai diễn trong phim {movie1}, đánh bại 4 đối thủ nặng ký khác.",
                "5 bộ phim kinh điển mọi thời đại?",
                "Lịch chiếu phim {movie1} cuối tuần này?"
            ],
            "football": [
                "Kết quả Champions League?",
                "BXH Ngoại hạng Anh sau vòng 30?",
                "Chuyển nhượng bóng đá?",
                "Lịch thi đấu vòng tứ kết World Cup?",
                "Tổng hợp bàn thắng đẹp nhất tuần?",
                "Thống kê {player1} mùa này?"
            ],
            "technology": [
                "So sánh iPhone 16 Pro và Samsung S24 Ultra?",
                "5 tính năng AI mới trên smartphone 2024?",
                "Đánh giá laptop gaming {laptop_model}?",
                "Cách tối ưu hóa pin điện thoại tăng 30% thời lượng?",
                "3 ứng dụng quản lý công việc tốt nhất 2024?",
                "Tin công nghệ?"
            ],
            "health": [
                "5 loại thực phẩm tăng cường miễn dịch mùa {season}?",
                "Chế độ ăn Địa Trung Hải giúp giảm 30% nguy cơ bệnh tim mạch?",
                "3 bài tập cardio đốt mỡ bụng hiệu quả trong 15 phút?",
                "Nghiên cứu mới?",
                "Cách phòng tránh cảm cúm mùa {season}?",
                "Thực đơn 7 ngày giàu protein?"
            ],
            "family": [
                "10 hoạt động cuối tuần gắn kết gia đình?",
                "5 trò chơi phát triển IQ cho trẻ 3-6 tuổi?.",
                "Bí quyết dạy trẻ quản lý tài chính?",
                "Lịch trình khoa học cho trẻ?",
                "Cách giải quyết mâu thuẫn anh chị em?",
                "5 dấu hiệu trẻ gặp khó khăn tâm lý cần hỗ trợ?"
            ],
            "travel": [
                "Top 5 điểm du lịch Việt Nam mùa {season}?",
                "Kinh nghiệm du lịch tiết kiệm?",
                "Lịch trình du lịch Đà Nẵng 3 ngày?",
                "5 món đặc sản không thể bỏ qua khi đến Huế?",
                "Cách chuẩn bị hành lý cho chuyến du lịch 5 ngày?",
                "Kinh nghiệm đặt phòng khách sạn?"
            ],
            "news": [
                "Tin kinh tế?",
                "Tin thời tiết?",
                "Tin giáo dục?",
                "Tin giao thông?",
                "Tin y tế?",
                "Tin văn hóa?"
            ]
        }
        
        # Các biến thay thế trong mẫu câu
        replacements = {
            "food": ["phở", "bánh mì", "cơm rang", "gỏi cuốn", "bún chả", "bánh xèo", "mì Ý", "sushi", "pizza", "món Hàn Quốc"],
            "meal": ["sáng", "trưa", "tối", "xế"],
            "event": ["sinh nhật", "họp gia đình", "dã ngoại", "tiệc", "kỳ nghỉ"],
            "days": ["vài", "2", "3", "7", "10"],
            "hobby": ["đọc sách", "nấu ăn", "thể thao", "làm vườn", "vẽ", "âm nhạc", "nhiếp ảnh"],
            "time_of_day": ["sáng", "trưa", "chiều", "tối"],
            "day": ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ Nhật", "cuối tuần"],
            "season": ["xuân", "hạ", "thu", "đông"],
            "weather": ["nóng", "lạnh", "mưa", "nắng", "gió"],
            "music_artist": ["Sơn Tùng M-TP", "Mỹ Tâm", "BTS", "Taylor Swift", "Adele", "Coldplay", "BlackPink"],
            "actor": ["Ngô Thanh Vân", "Trấn Thành", "Tom Cruise", "Song Joong Ki", "Scarlett Johansson", "Leonardo DiCaprio"],
            "movie1": ["The Beekeeper", "Dune 2", "Godzilla x Kong", "Deadpool 3", "Inside Out 2", "Twisters", "Bad Boys 4"],
            "movie2": ["The Fall Guy", "Kingdom of the Planet of the Apes", "Furiosa", "Borderlands", "Alien: Romulus"],
            "movie3": ["Gladiator 2", "Wicked", "Sonic the Hedgehog 3", "Mufasa", "Moana 2", "Venom 3"],
            "team1": ["Manchester City", "Arsenal", "Liverpool", "Real Madrid", "Barcelona", "Bayern Munich", "PSG", "Việt Nam"],
            "team2": ["Chelsea", "Tottenham", "Inter Milan", "Juventus", "Atletico Madrid", "Dortmund", "Thái Lan"],
            "team3": ["Manchester United", "Newcastle", "AC Milan", "Napoli", "Porto", "Ajax", "Indonesia"],
            "team4": ["West Ham", "Aston Villa", "Roma", "Lazio", "Sevilla", "Leipzig", "Malaysia"],
            "player1": ["Haaland", "Salah", "Saka", "Bellingham", "Mbappe", "Martinez", "Quang Hải", "Tiến Linh"],
            "player2": ["De Bruyne", "Odegaard", "Kane", "Vinicius", "Lewandowski", "Griezmann", "Công Phượng"],
            "player3": ["Rodri", "Rice", "Son", "Kroos", "Pedri", "Messi", "Văn Hậu", "Văn Lâm"],
            "score1": ["1", "2", "3", "4", "5"],
            "score2": ["0", "1", "2", "3"],
            "minute1": ["12", "23", "45+2", "56", "67", "78", "89+1"],
            "minute2": ["34", "45", "59", "69", "80", "90+3"],
            "gameday": ["thứ Bảy", "Chủ nhật", "20/4", "27/4", "4/5", "11/5", "18/5"],
            "laptop_model": ["Asus ROG Zephyrus G14", "Lenovo Legion Pro 7", "MSI Titan GT77", "Acer Predator Helios", "Alienware m18"]
        }
        
        # Thay thế các biến bằng thông tin cá nhân nếu có
        if member_id and member_id in family_data:
            preferences = family_data[member_id].get("preferences", {})
            
            if preferences.get("food"):
                replacements["food"].insert(0, preferences["food"])
            
            if preferences.get("hobby"):
                replacements["hobby"].insert(0, preferences["hobby"])
        
        # Thêm thông tin từ sự kiện sắp tới
        if upcoming_events:
            for event in upcoming_events:
                replacements["event"].insert(0, event["title"])
                replacements["days"].insert(0, str(event["days_away"]))
        
        # Xác định mùa hiện tại (đơn giản hóa)
        current_month = datetime.datetime.now().month
        if 3 <= current_month <= 5:
            current_season = "xuân"
        elif 6 <= current_month <= 8:
            current_season = "hạ"
        elif 9 <= current_month <= 11:
            current_season = "thu"
        else:
            current_season = "đông"
        
        replacements["season"].insert(0, current_season)
        
        # Thêm ngày hiện tại
        current_day_name = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"][datetime.datetime.now().weekday()]
        replacements["day"].insert(0, current_day_name)
        
        # Thêm bữa ăn phù hợp với thời điểm hiện tại
        current_hour = datetime.datetime.now().hour
        if 5 <= current_hour < 10:
            current_meal = "sáng"
        elif 10 <= current_hour < 14:
            current_meal = "trưa"
        elif 14 <= current_hour < 17:
            current_meal = "xế"
        else:
            current_meal = "tối"
        
        replacements["meal"].insert(0, current_meal)
        replacements["time_of_day"].insert(0, current_meal)
        
        # Tạo danh sách các chủ đề ưu tiên theo sở thích người dùng
        priority_categories = []
        user_preferences = {}
        
        # Phân tích sở thích người dùng
        if member_id and member_id in family_data:
            preferences = family_data[member_id].get("preferences", {})
            user_preferences = preferences
            
            # Ưu tiên các chủ đề dựa trên sở thích
            if preferences.get("food"):
                priority_categories.append("food")
            
            if preferences.get("hobby"):
                hobby = preferences["hobby"].lower()
                if any(keyword in hobby for keyword in ["đọc", "sách", "học", "nghiên cứu"]):
                    priority_categories.append("education")
                elif any(keyword in hobby for keyword in ["du lịch", "đi", "khám phá", "phiêu lưu"]):
                    priority_categories.append("travel")
                elif any(keyword in hobby for keyword in ["âm nhạc", "nghe", "hát", "nhạc"]):
                    priority_categories.append("entertainment")
                elif any(keyword in hobby for keyword in ["phim", "xem", "điện ảnh", "movie"]):
                    priority_categories.append("movies")
                elif any(keyword in hobby for keyword in ["bóng đá", "thể thao", "bóng rổ", "thể hình", "gym", "bóng", "đá", "tennis"]):
                    priority_categories.append("football")
                elif any(keyword in hobby for keyword in ["công nghệ", "máy tính", "điện thoại", "game", "tech"]):
                    priority_categories.append("technology")
                
        # Luôn đảm bảo có tin tức trong các gợi ý
        priority_categories.append("news")
        
        # Thêm các chủ đề còn lại
        remaining_categories = [cat for cat in question_templates.keys() if cat not in priority_categories]
        
        # Đảm bảo tách riêng phim và bóng đá nếu người dùng thích cả hai
        if "movies" not in priority_categories and "football" not in priority_categories:
            # Nếu cả hai chưa được thêm, thêm cả hai
            remaining_categories = ["movies", "football"] + [cat for cat in remaining_categories if cat not in ["movies", "football"]]
        
        # Kết hợp để có tất cả chủ đề
        all_categories = priority_categories + remaining_categories
        
        # Chọn tối đa max_questions chủ đề, đảm bảo ưu tiên các sở thích
        selected_categories = all_categories[:max_questions]
        
        # Tạo câu gợi ý cho mỗi chủ đề
        for category in selected_categories:
            if len(questions) >= max_questions:
                break
                
            # Chọn một mẫu câu ngẫu nhiên từ chủ đề
            template = random.choice(question_templates[category])
            
            # Điều chỉnh mẫu câu dựa trên sở thích người dùng
            if category == "food" and user_preferences.get("food"):
                # Nếu người dùng có món ăn yêu thích, thay thế biến {food} bằng sở thích
                template = template.replace("{food}", user_preferences["food"])
            elif category == "football" and "hobby" in user_preferences and any(keyword in user_preferences["hobby"].lower() for keyword in ["bóng đá", "thể thao"]):
                # Nếu người dùng thích bóng đá, ưu tiên thông tin cụ thể hơn
                pass  # Giữ nguyên template vì đã đủ cụ thể
            
            # Thay thế các biến còn lại trong mẫu câu
            question = template
            for key in replacements:
                if "{" + key + "}" in question:
                    replacement = random.choice(replacements[key])
                    question = question.replace("{" + key + "}", replacement)
            
            questions.append(question)
        
        # Đảm bảo đủ số lượng câu hỏi
        if len(questions) < max_questions:
            # Ưu tiên thêm từ tin tức và thông tin giải trí
            more_templates = []
            more_templates.extend(question_templates["news"])
            more_templates.extend(question_templates["movies"])
            more_templates.extend(question_templates["football"])
            
            random.shuffle(more_templates)
            
            while len(questions) < max_questions and more_templates:
                template = more_templates.pop(0)
                
                # Thay thế các biến trong mẫu câu
                question = template
                for key in replacements:
                    if "{" + key + "}" in question:
                        replacement = random.choice(replacements[key])
                        question = question.replace("{" + key + "}", replacement)
                
                # Tránh trùng lặp
                if question not in questions:
                    questions.append(question)
    
    # Lưu câu hỏi vào cache
    if "question_cache" not in st.session_state:
        st.session_state.question_cache = {}
    
    st.session_state.question_cache[cache_key] = questions
    
    return questions

def handle_suggested_question(question):
    """Xử lý khi người dùng chọn câu hỏi gợi ý"""
    st.session_state.suggested_question = question
    st.session_state.process_suggested = True

# Thêm các hàm tiện ích cho việc tính toán ngày tháng
def get_date_from_relative_term(term):
    """Chuyển đổi từ mô tả tương đối về ngày thành ngày thực tế"""
    today = datetime.datetime.now().date()
    
    if term in ["hôm nay", "today"]:
        return today
    elif term in ["ngày mai", "mai", "tomorrow"]:
        return today + datetime.timedelta(days=1)
    elif term in ["ngày kia", "day after tomorrow"]:
        return today + datetime.timedelta(days=2)
    elif term in ["hôm qua", "yesterday"]:
        return today - datetime.timedelta(days=1)
    elif "tuần tới" in term or "tuần sau" in term or "next week" in term:
        return today + datetime.timedelta(days=7)
    elif "tuần trước" in term or "last week" in term:
        return today - datetime.timedelta(days=7)
    elif "tháng tới" in term or "tháng sau" in term or "next month" in term:
        # Đơn giản hóa bằng cách thêm 30 ngày
        return today + datetime.timedelta(days=30)
    
    return None

# Tải dữ liệu ban đầu
def load_data(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Đảm bảo dữ liệu là một từ điển
                if not isinstance(data, dict):
                    print(f"Dữ liệu trong {file_path} không phải từ điển. Khởi tạo lại.")
                    return {}
                return data
        except Exception as e:
            print(f"Lỗi khi đọc {file_path}: {e}")
            return {}
    return {}

def save_data(file_path, data):
    try:
        # Đảm bảo thư mục tồn tại
        os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info(f"Đã lưu dữ liệu vào {file_path}: {len(data)} mục")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi lưu dữ liệu vào {file_path}: {e}")
        st.error(f"Không thể lưu dữ liệu: {e}")
        return False

# Kiểm tra và đảm bảo cấu trúc dữ liệu đúng
def verify_data_structure():
    global family_data, events_data, notes_data, chat_history
    
    # Đảm bảo tất cả dữ liệu là từ điển
    if not isinstance(family_data, dict):
        print("family_data không phải từ điển. Khởi tạo lại.")
        family_data = {}
        
    if not isinstance(events_data, dict):
        print("events_data không phải từ điển. Khởi tạo lại.")
        events_data = {}
        
    if not isinstance(notes_data, dict):
        print("notes_data không phải từ điển. Khởi tạo lại.")
        notes_data = {}
        
    if not isinstance(chat_history, dict):
        print("chat_history không phải từ điển. Khởi tạo lại.")
        chat_history = {}
    
    # Kiểm tra và sửa các dữ liệu thành viên
    members_to_fix = []
    for member_id, member in family_data.items():
        if not isinstance(member, dict):
            members_to_fix.append(member_id)
    
    # Xóa các mục không hợp lệ
    for member_id in members_to_fix:
        del family_data[member_id]
        
    # Lưu lại dữ liệu đã sửa
    save_data(FAMILY_DATA_FILE, family_data)
    save_data(EVENTS_DATA_FILE, events_data)
    save_data(NOTES_DATA_FILE, notes_data)
    save_data(CHAT_HISTORY_FILE, chat_history)

# Tải dữ liệu ban đầu
family_data = load_data(FAMILY_DATA_FILE)
events_data = load_data(EVENTS_DATA_FILE)
notes_data = load_data(NOTES_DATA_FILE)
chat_history = load_data(CHAT_HISTORY_FILE)  # Tải lịch sử chat

# Kiểm tra và sửa cấu trúc dữ liệu
verify_data_structure()

# Hàm chuyển đổi hình ảnh sang base64
def get_image_base64(image_raw):
    buffered = BytesIO()
    image_raw.save(buffered, format=image_raw.format)
    img_byte = buffered.getvalue()
    return base64.b64encode(img_byte).decode('utf-8')

# Hàm tạo tóm tắt lịch sử chat
def generate_chat_summary(messages, api_key):
    """Tạo tóm tắt từ lịch sử trò chuyện"""
    if not messages or len(messages) < 3:  # Cần ít nhất một vài tin nhắn để tạo tóm tắt
        return "Chưa có đủ tin nhắn để tạo tóm tắt."
    
    # Chuẩn bị dữ liệu cho API
    content_texts = []
    for message in messages:
        if "content" in message:
            # Xử lý cả tin nhắn văn bản và hình ảnh
            if isinstance(message["content"], list):
                for content in message["content"]:
                    if content["type"] == "text":
                        content_texts.append(f"{message['role'].upper()}: {content['text']}")
            else:
                content_texts.append(f"{message['role'].upper()}: {message['content']}")
    
    # Ghép tất cả nội dung lại
    full_content = "\n".join(content_texts)
    
    # Gọi API để tạo tóm tắt
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=openai_model,
            messages=[
                {"role": "system", "content": "Bạn là trợ lý tạo tóm tắt. Hãy tóm tắt cuộc trò chuyện dưới đây thành 1-3 câu ngắn gọn, tập trung vào các thông tin và yêu cầu chính."},
                {"role": "user", "content": f"Tóm tắt cuộc trò chuyện sau:\n\n{full_content}"}
            ],
            temperature=0.3,
            max_tokens=150
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Lỗi khi tạo tóm tắt: {e}")
        return "Không thể tạo tóm tắt vào lúc này."

# Hàm lưu lịch sử trò chuyện cho người dùng hiện tại
def save_chat_history(member_id, messages, summary=None):
    """Lưu lịch sử chat cho một thành viên cụ thể"""
    if member_id not in chat_history:
        chat_history[member_id] = []
    
    # Tạo bản ghi mới
    history_entry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "messages": messages,
        "summary": summary if summary else ""
    }
    
    # Thêm vào lịch sử và giới hạn số lượng
    chat_history[member_id].insert(0, history_entry)  # Thêm vào đầu danh sách
    
    # Giới hạn lưu tối đa 10 cuộc trò chuyện gần nhất
    if len(chat_history[member_id]) > 10:
        chat_history[member_id] = chat_history[member_id][:10]
    
    # Lưu vào file
    save_data(CHAT_HISTORY_FILE, chat_history)

# Phát hiện câu hỏi cần search thông tin thực tế
def detect_search_intent(query, api_key):
    """
    Phát hiện xem câu hỏi có cần tìm kiếm thông tin thực tế hay không, và trích xuất thông tin thời gian
    
    Args:
        query (str): Câu hỏi của người dùng
        api_key (str): OpenAI API key
        
    Returns:
        tuple: (need_search, search_query, time_info)
    """
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=openai_model,
            messages=[
                {"role": "system", "content": """
                    Bạn là một hệ thống phân loại câu hỏi thông minh. Nhiệm vụ của bạn là xác định xem câu hỏi có cần tìm kiếm thông tin thực tế, tin tức mới hoặc dữ liệu cập nhật không.
                    
                    Câu hỏi cần search khi:
                    1. Liên quan đến tin tức, sự kiện hiện tại hoặc gần đây
                    2. Yêu cầu dữ liệu thực tế, số liệu thống kê cập nhật
                    3. Hỏi về kết quả thể thao, giải đấu
                    4. Cần thông tin về giá cả, sản phẩm mới
                    5. Liên quan đến thời tiết, tình hình giao thông hiện tại
                    
                    Câu hỏi KHÔNG cần search khi:
                    1. Liên quan đến quản lý gia đình (thêm thành viên, sự kiện, ghi chú)
                    2. Hỏi ý kiến, lời khuyên cá nhân
                    3. Yêu cầu công thức nấu ăn phổ biến
                    4. Câu hỏi đơn giản về kiến thức phổ thông
                    5. Yêu cầu hỗ trợ sử dụng ứng dụng
                    
                    QUAN TRỌNG: Nếu câu hỏi đề cập đến một thời điểm cụ thể (hôm nay, ngày mai, hôm qua, ngày 12/05, tuần trước, tuần này, tháng này, v.v.), 
                    hãy phân tích và trích xuất thông tin thời gian này để sử dụng trong truy vấn tìm kiếm.
                """},
                {"role": "user", "content": f"Câu hỏi: {query}\n\nCâu hỏi này có cần tìm kiếm thông tin thực tế không? Trả lời JSON với 3 trường: need_search (true/false), search_query (câu truy vấn tìm kiếm tối ưu nếu cần search), và time_info (thông tin về thời gian cụ thể được đề cập trong câu hỏi, để trống nếu không có)."}
            ],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        return result.get("need_search", False), result.get("search_query", query), result.get("time_info", "")
    
    except Exception as e:
        logger.error(f"Lỗi khi phát hiện ý định tìm kiếm: {e}")
        return False, query, ""

# Hàm stream phản hồi từ GPT-4o-mini
def stream_llm_response(api_key, system_prompt="", current_member=None):
    """Hàm tạo và xử lý phản hồi từ mô hình AI"""
    response_message = ""
    
    # Tạo tin nhắn với system prompt
    messages = [{"role": "system", "content": system_prompt}]
    
    # Thêm tất cả tin nhắn trước đó vào cuộc trò chuyện
    for message in st.session_state.messages:
        # Xử lý các tin nhắn hình ảnh
        if any(content["type"] == "image_url" for content in message["content"]):
            # Đối với tin nhắn có hình ảnh, chúng ta cần tạo tin nhắn theo định dạng của OpenAI
            images = [content for content in message["content"] if content["type"] == "image_url"]
            texts = [content for content in message["content"] if content["type"] == "text"]
            
            # Thêm hình ảnh và văn bản vào tin nhắn
            message_content = []
            for image in images:
                message_content.append({
                    "type": "image_url",
                    "image_url": {"url": image["image_url"]["url"]}
                })
            
            if texts:
                text_content = "\n".join([text["text"] for text in texts])
                message_content.append({
                    "type": "text",
                    "text": text_content
                })
            
            messages.append({
                "role": message["role"],
                "content": message_content
            })
        else:
            # Đối với tin nhắn chỉ có văn bản
            text_content = message["content"][0]["text"] if message["content"] else ""
            messages.append({
                "role": message["role"],
                "content": text_content
            })
    
    try:
        # Lấy tin nhắn người dùng mới nhất
        last_user_message = ""
        for message in reversed(st.session_state.messages):
            if message["role"] == "user" and message["content"][0]["type"] == "text":
                last_user_message = message["content"][0]["text"]
                break
        
        # Phát hiện ý định tìm kiếm
        need_search = False
        search_query = ""
        time_info = ""

        if last_user_message:
            tavily_api_key = st.session_state.get("tavily_api_key", "")
            if tavily_api_key:
                # Hiển thị placeholder để người dùng biết trợ lý đang tìm kiếm
                placeholder = st.empty()
                placeholder.info("🔍 Đang phân tích câu hỏi của bạn...")
                
                need_search, search_query, time_info = detect_search_intent(last_user_message, api_key)
                
                if need_search:
                    search_message = f"🔍 Đang tìm kiếm thông tin về: '{search_query}'"
                    if time_info:
                        search_message += f" ({time_info})"
                    placeholder.info(search_message)
                    
                    search_result = search_and_summarize(tavily_api_key, search_query, api_key, time_info)
                    
                    # Thêm kết quả tìm kiếm vào hệ thống prompt
                    time_context = f" cho '{time_info}'" if time_info else ""
                    search_info = f"""
                    THÔNG TIN TÌM KIẾM{time_context}:
                    Câu hỏi: {search_query}
                    
                    Kết quả:
                    {search_result}
                    
                    Hãy sử dụng thông tin này để trả lời câu hỏi của người dùng. Đảm bảo đề cập đến nguồn thông tin.
                    """
                    
                    messages[0]["content"] = system_prompt + "\n\n" + search_info
                    placeholder.empty()
        
        client = OpenAI(api_key=api_key)
        for chunk in client.chat.completions.create(
            model=openai_model,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
            stream=True,
        ):
            chunk_text = chunk.choices[0].delta.content or ""
            response_message += chunk_text
            yield chunk_text

        # Hiển thị phản hồi đầy đủ trong log để debug
        logger.info(f"Phản hồi đầy đủ từ trợ lý: {response_message[:200]}...")
        
        # Xử lý phản hồi để trích xuất lệnh
        process_assistant_response(response_message, current_member)
        
        # Thêm phản hồi vào session state
        st.session_state.messages.append({
            "role": "assistant", 
            "content": [
                {
                    "type": "text",
                    "text": response_message,
                }
            ]})
        
        # Nếu đang chat với một thành viên cụ thể, lưu lịch sử
        if current_member:
            # Tạo tóm tắt cuộc trò chuyện
            summary = generate_chat_summary(st.session_state.messages, api_key)
            # Lưu lịch sử
            save_chat_history(current_member, st.session_state.messages, summary)
            
    except Exception as e:
        logger.error(f"Lỗi khi tạo phản hồi từ OpenAI: {e}")
        error_message = f"Có lỗi xảy ra: {str(e)}"
        yield error_message

def process_assistant_response(response, current_member=None):
    """Hàm xử lý lệnh từ phản hồi của trợ lý"""
    try:
        logger.info(f"Xử lý phản hồi của trợ lý, độ dài: {len(response)}")
        
        # Xử lý lệnh thêm sự kiện
        if "##ADD_EVENT:" in response:
            logger.info("Tìm thấy lệnh ADD_EVENT")
            cmd_start = response.index("##ADD_EVENT:") + len("##ADD_EVENT:")
            cmd_end = response.index("##", cmd_start)
            cmd = response[cmd_start:cmd_end].strip()
            
            logger.info(f"Nội dung lệnh ADD_EVENT: {cmd}")
            
            try:
                details = json.loads(cmd)
                if isinstance(details, dict):
                    # Xử lý các từ ngữ tương đối về thời gian
                    logger.info(f"Đang xử lý ngày: {details.get('date', '')}")
                    if details.get('date') and not details['date'][0].isdigit():
                        # Nếu ngày không bắt đầu bằng số, có thể là mô tả tương đối
                        relative_date = get_date_from_relative_term(details['date'].lower())
                        if relative_date:
                            details['date'] = relative_date.strftime("%Y-%m-%d")
                            logger.info(f"Đã chuyển đổi ngày thành: {details['date']}")
                    
                    # Thêm thông tin về người tạo sự kiện
                    if current_member:
                        details['created_by'] = current_member
                    
                    logger.info(f"Thêm sự kiện: {details.get('title', 'Không tiêu đề')}")
                    success = add_event(details)
                    if success:
                        st.success(f"Đã thêm sự kiện: {details.get('title', '')}")
            except json.JSONDecodeError as e:
                logger.error(f"Lỗi khi phân tích JSON cho ADD_EVENT: {e}")
                logger.error(f"Chuỗi JSON gốc: {cmd}")
        
        # Xử lý lệnh UPDATE_EVENT
        if "##UPDATE_EVENT:" in response:
            logger.info("Tìm thấy lệnh UPDATE_EVENT")
            cmd_start = response.index("##UPDATE_EVENT:") + len("##UPDATE_EVENT:")
            cmd_end = response.index("##", cmd_start)
            cmd = response[cmd_start:cmd_end].strip()
            
            logger.info(f"Nội dung lệnh UPDATE_EVENT: {cmd}")
            
            try:
                details = json.loads(cmd)
                if isinstance(details, dict):
                    # Xử lý các từ ngữ tương đối về thời gian
                    if details.get('date') and not details['date'][0].isdigit():
                        # Nếu ngày không bắt đầu bằng số, có thể là mô tả tương đối
                        relative_date = get_date_from_relative_term(details['date'].lower())
                        if relative_date:
                            details['date'] = relative_date.strftime("%Y-%m-%d")
                    
                    logger.info(f"Cập nhật sự kiện: {details.get('title', 'Không tiêu đề')}")
                    success = update_event(details)
                    if success:
                        st.success(f"Đã cập nhật sự kiện: {details.get('title', '')}")
            except json.JSONDecodeError as e:
                logger.error(f"Lỗi khi phân tích JSON cho UPDATE_EVENT: {e}")
        
        # Các lệnh xử lý khác tương tự
        for cmd_type in ["ADD_FAMILY_MEMBER", "UPDATE_PREFERENCE", "DELETE_EVENT", "ADD_NOTE"]:
            cmd_pattern = f"##{cmd_type}:"
            if cmd_pattern in response:
                logger.info(f"Tìm thấy lệnh {cmd_type}")
                try:
                    cmd_start = response.index(cmd_pattern) + len(cmd_pattern)
                    cmd_end = response.index("##", cmd_start)
                    cmd = response[cmd_start:cmd_end].strip()
                    
                    if cmd_type == "DELETE_EVENT":
                        event_id = cmd.strip()
                        delete_event(event_id)
                        st.success(f"Đã xóa sự kiện!")
                    else:
                        details = json.loads(cmd)
                        if isinstance(details, dict):
                            if cmd_type == "ADD_FAMILY_MEMBER":
                                add_family_member(details)
                                st.success(f"Đã thêm thành viên: {details.get('name', '')}")
                            elif cmd_type == "UPDATE_PREFERENCE":
                                update_preference(details)
                                st.success(f"Đã cập nhật sở thích!")
                            elif cmd_type == "ADD_NOTE":
                                # Thêm thông tin về người tạo ghi chú
                                if current_member:
                                    details['created_by'] = current_member
                                add_note(details)
                                st.success(f"Đã thêm ghi chú!")
                except Exception as e:
                    logger.error(f"Lỗi khi xử lý lệnh {cmd_type}: {e}")
    
    except Exception as e:
        logger.error(f"Lỗi khi xử lý phản hồi của trợ lý: {e}")
        logger.error(f"Phản hồi gốc: {response[:100]}...")

# Các hàm quản lý thông tin gia đình
def add_family_member(details):
    member_id = details.get("id") or str(len(family_data) + 1)
    family_data[member_id] = {
        "name": details.get("name", ""),
        "age": details.get("age", ""),
        "preferences": details.get("preferences", {}),
        "added_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_data(FAMILY_DATA_FILE, family_data)

def update_preference(details):
    member_id = details.get("id")
    preference_key = details.get("key")
    preference_value = details.get("value")
    
    if member_id in family_data and preference_key:
        if "preferences" not in family_data[member_id]:
            family_data[member_id]["preferences"] = {}
        family_data[member_id]["preferences"][preference_key] = preference_value
        save_data(FAMILY_DATA_FILE, family_data)

def add_event(details):
    """Thêm một sự kiện mới vào danh sách sự kiện"""
    try:
        event_id = str(len(events_data) + 1)
        events_data[event_id] = {
            "title": details.get("title", ""),
            "date": details.get("date", ""),
            "time": details.get("time", ""),
            "description": details.get("description", ""),
            "participants": details.get("participants", []),
            "created_by": details.get("created_by", ""),  # Thêm người tạo sự kiện
            "created_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_data(EVENTS_DATA_FILE, events_data)
        print(f"Đã thêm sự kiện: {details.get('title', '')} vào {EVENTS_DATA_FILE}")
        print(f"Tổng số sự kiện hiện tại: {len(events_data)}")
        return True
    except Exception as e:
        print(f"Lỗi khi thêm sự kiện: {e}")
        return False

def update_event(details):
    """Cập nhật thông tin về một sự kiện"""
    try:
        event_id = details.get("id")
        if event_id in events_data:
            # Cập nhật các trường được cung cấp
            for key, value in details.items():
                if key != "id" and value is not None:
                    events_data[event_id][key] = value
            
            # Đảm bảo trường created_on được giữ nguyên
            if "created_on" not in events_data[event_id]:
                events_data[event_id]["created_on"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            save_data(EVENTS_DATA_FILE, events_data)
            logger.info(f"Đã cập nhật sự kiện ID={event_id}: {details}")
            return True
        else:
            logger.warning(f"Không tìm thấy sự kiện ID={event_id}")
            return False
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật sự kiện: {e}")
        return False

def delete_event(event_id):
    if event_id in events_data:
        del events_data[event_id]
        save_data(EVENTS_DATA_FILE, events_data)

# Các hàm quản lý ghi chú
def add_note(details):
    note_id = str(len(notes_data) + 1)
    notes_data[note_id] = {
        "title": details.get("title", ""),
        "content": details.get("content", ""),
        "tags": details.get("tags", []),
        "created_by": details.get("created_by", ""),  # Thêm người tạo ghi chú
        "created_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_data(NOTES_DATA_FILE, notes_data)

# Lọc sự kiện theo người dùng
def filter_events_by_member(member_id=None):
    """Lọc sự kiện theo thành viên cụ thể"""
    if not member_id:
        return events_data  # Trả về tất cả sự kiện nếu không có ID
    
    filtered_events = {}
    for event_id, event in events_data.items():
        # Lọc những sự kiện mà thành viên tạo hoặc tham gia
        if (event.get("created_by") == member_id or 
            (member_id in family_data and 
             family_data[member_id].get("name") in event.get("participants", []))):
            filtered_events[event_id] = event
    
    return filtered_events

def main():
    # --- Cấu hình trang ---
    st.set_page_config(
        page_title="Trợ lý Gia đình",
        page_icon="👨‍👩‍👧‍👦",
        layout="centered",
        initial_sidebar_state="expanded",
    )

    # --- Tiêu đề ---
    st.html("""<h1 style="text-align: center; color: #6ca395;">👨‍👩‍👧‍👦 <i>Trợ lý Gia đình</i> 💬</h1>""")
    
    # --- Khởi tạo session state ---
    if "current_member" not in st.session_state:
        st.session_state.current_member = None  # ID thành viên đang trò chuyện
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "suggested_question" not in st.session_state:
        st.session_state.suggested_question = None
    if "process_suggested" not in st.session_state:
        st.session_state.process_suggested = False
    if "question_cache" not in st.session_state:
        st.session_state.question_cache = {}
    if "tavily_api_key" not in st.session_state:
        st.session_state.tavily_api_key = ""

    # --- Thanh bên ---
    with st.sidebar:
        default_openai_api_key = os.getenv("OPENAI_API_KEY", "")
        default_tavily_api_key = os.getenv("TAVILY_API_KEY", "")
        
        with st.popover("🔐 API Keys"):
            openai_api_key = st.text_input("OpenAI API Key:", value=default_openai_api_key, type="password")
            tavily_api_key = st.text_input("Tavily API Key:", value=default_tavily_api_key, type="password")
            st.session_state.tavily_api_key = tavily_api_key
            
            if tavily_api_key:
                st.success("✅ Tính năng tìm kiếm thời gian thực đã được kích hoạt!")
            else:
                st.warning("⚠️ Vui lòng nhập Tavily API Key để kích hoạt tính năng tìm kiếm thông tin thời gian thực.")
        
        # Chọn người dùng hiện tại
        st.write("## 👤 Chọn người dùng")
        
        # Tạo danh sách tên thành viên và ID
        member_options = {"Chung (Không cá nhân hóa)": None}
        for member_id, member in family_data.items():
            if isinstance(member, dict) and "name" in member:
                member_options[member["name"]] = member_id
        
        # Dropdown chọn người dùng
        selected_member_name = st.selectbox(
            "Bạn đang trò chuyện với tư cách ai?",
            options=list(member_options.keys()),
            index=0
        )
        
        # Cập nhật người dùng hiện tại
        new_member_id = member_options[selected_member_name]
        
        # Nếu người dùng thay đổi, cập nhật session state và khởi tạo lại tin nhắn
        if new_member_id != st.session_state.current_member:
            st.session_state.current_member = new_member_id
            if "messages" in st.session_state:
                st.session_state.pop("messages", None)
                st.rerun()
        
        # Hiển thị thông tin người dùng hiện tại
        if st.session_state.current_member:
            member = family_data[st.session_state.current_member]
            st.info(f"Đang trò chuyện với tư cách: **{member.get('name')}**")
            
            # Hiển thị lịch sử trò chuyện trước đó
            if st.session_state.current_member in chat_history and chat_history[st.session_state.current_member]:
                with st.expander("📜 Lịch sử trò chuyện trước đó"):
                    for idx, history in enumerate(chat_history[st.session_state.current_member]):
                        st.write(f"**{history.get('timestamp')}**")
                        st.write(f"*{history.get('summary', 'Không có tóm tắt')}*")
                        
                        # Nút để tải lại cuộc trò chuyện cũ
                        if st.button(f"Tải lại cuộc trò chuyện này", key=f"load_chat_{idx}"):
                            st.session_state.messages = history.get('messages', [])
                            st.rerun()
                        st.divider()
        
        st.write("## Thông tin Gia đình")
        
        # Phần thêm thành viên gia đình
        with st.expander("➕ Thêm thành viên gia đình"):
            with st.form("add_family_form"):
                member_name = st.text_input("Tên")
                member_age = st.text_input("Tuổi")
                st.write("Sở thích:")
                food_pref = st.text_input("Món ăn yêu thích")
                hobby_pref = st.text_input("Sở thích")
                color_pref = st.text_input("Màu yêu thích")
                
                add_member_submitted = st.form_submit_button("Thêm")
                
                if add_member_submitted and member_name:
                    member_id = str(len(family_data) + 1)
                    family_data[member_id] = {
                        "name": member_name,
                        "age": member_age,
                        "preferences": {
                            "food": food_pref,
                            "hobby": hobby_pref,
                            "color": color_pref
                        },
                        "added_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_data(FAMILY_DATA_FILE, family_data)
                    st.success(f"Đã thêm {member_name} vào gia đình!")
        
        # Xem và chỉnh sửa thành viên gia đình
        with st.expander("👥 Thành viên gia đình"):
            if not family_data:
                st.write("Chưa có thành viên nào trong gia đình")
            else:
                for member_id, member in family_data.items():
                    # Kiểm tra kiểu dữ liệu của member
                    if isinstance(member, dict):
                        # Sử dụng get() khi member là dict
                        member_name = member.get("name", "Không tên")
                        member_age = member.get("age", "")
                        
                        st.write(f"**{member_name}** ({member_age})")
                        
                        # Hiển thị sở thích
                        if "preferences" in member and isinstance(member["preferences"], dict):
                            for pref_key, pref_value in member["preferences"].items():
                                if pref_value:
                                    st.write(f"- {pref_key.capitalize()}: {pref_value}")
                        
                        # Nút chỉnh sửa cho mỗi thành viên
                        if st.button(f"Chỉnh sửa {member_name}", key=f"edit_{member_id}"):
                            st.session_state.editing_member = member_id
                    else:
                        # Xử lý khi member không phải dict
                        st.error(f"Dữ liệu thành viên ID={member_id} không đúng định dạng")
        
        # Form chỉnh sửa thành viên (xuất hiện khi đang chỉnh sửa)
        if "editing_member" in st.session_state and st.session_state.editing_member:
            member_id = st.session_state.editing_member
            if member_id in family_data and isinstance(family_data[member_id], dict):
                member = family_data[member_id]
                
                with st.form(f"edit_member_{member_id}"):
                    st.write(f"Chỉnh sửa: {member.get('name', 'Không tên')}")
                    
                    # Các trường chỉnh sửa
                    new_name = st.text_input("Tên", member.get("name", ""))
                    new_age = st.text_input("Tuổi", member.get("age", ""))
                    
                    # Sở thích
                    st.write("Sở thích:")
                    prefs = member.get("preferences", {}) if isinstance(member.get("preferences"), dict) else {}
                    new_food = st.text_input("Món ăn yêu thích", prefs.get("food", ""))
                    new_hobby = st.text_input("Sở thích", prefs.get("hobby", ""))
                    new_color = st.text_input("Màu yêu thích", prefs.get("color", ""))
                    
                    save_edits = st.form_submit_button("Lưu")
                    cancel_edits = st.form_submit_button("Hủy")
                    
                    if save_edits:
                        family_data[member_id]["name"] = new_name
                        family_data[member_id]["age"] = new_age
                        family_data[member_id]["preferences"] = {
                            "food": new_food,
                            "hobby": new_hobby,
                            "color": new_color
                        }
                        save_data(FAMILY_DATA_FILE, family_data)
                        st.session_state.editing_member = None
                        st.success("Đã cập nhật thông tin!")
                        st.rerun()
                    
                    if cancel_edits:
                        st.session_state.editing_member = None
                        st.rerun()
            else:
                st.error(f"Không tìm thấy thành viên với ID: {member_id}")
                st.session_state.editing_member = None
        
        st.divider()
        
        # Quản lý sự kiện
        st.write("## Sự kiện")
        
        # Phần thêm sự kiện
        with st.expander("📅 Thêm sự kiện"):
            with st.form("add_event_form"):
                event_title = st.text_input("Tiêu đề sự kiện")
                event_date = st.date_input("Ngày")
                event_time = st.time_input("Giờ")
                event_desc = st.text_area("Mô tả")
                
                # Multi-select cho người tham gia
                try:
                    member_names = [member.get("name", "") for member_id, member in family_data.items() 
                                   if isinstance(member, dict) and member.get("name")]
                    participants = st.multiselect("Người tham gia", member_names)
                except Exception as e:
                    st.error(f"Lỗi khi tải danh sách thành viên: {e}")
                    participants = []
                
                add_event_submitted = st.form_submit_button("Thêm sự kiện")
                
                if add_event_submitted and event_title:
                    event_id = str(len(events_data) + 1)
                    events_data[event_id] = {
                        "title": event_title,
                        "date": event_date.strftime("%Y-%m-%d"),
                        "time": event_time.strftime("%H:%M"),
                        "description": event_desc,
                        "participants": participants,
                        "created_by": st.session_state.current_member,  # Lưu người tạo
                        "created_on": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_data(EVENTS_DATA_FILE, events_data)
                    st.success(f"Đã thêm sự kiện: {event_title}!")
        
        # Xem sự kiện sắp tới - đã được lọc theo người dùng
        with st.expander("📆 Sự kiện"):
            # Lọc sự kiện theo người dùng hiện tại
            filtered_events = (
                filter_events_by_member(st.session_state.current_member) 
                if st.session_state.current_member 
                else events_data
            )
            
            # Phần hiển thị chế độ lọc
            mode = st.radio(
                "Chế độ hiển thị:",
                ["Tất cả sự kiện", "Sự kiện của tôi", "Sự kiện tôi tham gia"],
                horizontal=True,
                disabled=not st.session_state.current_member
            )
            
            # Lọc thêm theo chế độ được chọn
            display_events = {}
            current_member_name = ""
            if st.session_state.current_member:
                current_member_name = family_data[st.session_state.current_member].get("name", "")
            
            if mode == "Sự kiện của tôi" and st.session_state.current_member:
                for event_id, event in filtered_events.items():
                    if event.get("created_by") == st.session_state.current_member:
                        display_events[event_id] = event
            elif mode == "Sự kiện tôi tham gia" and current_member_name:
                for event_id, event in filtered_events.items():
                    if current_member_name in event.get("participants", []):
                        display_events[event_id] = event
            else:
                display_events = filtered_events
            
            # Sắp xếp sự kiện theo ngày (với xử lý lỗi)
            try:
                sorted_events = sorted(
                    display_events.items(),
                    key=lambda x: (x[1].get("date", ""), x[1].get("time", ""))
                )
            except Exception as e:
                st.error(f"Lỗi khi sắp xếp sự kiện: {e}")
                sorted_events = []
            
            if not sorted_events:
                st.write("Không có sự kiện nào")
            
            for event_id, event in sorted_events:
                st.write(f"**{event.get('title', 'Sự kiện không tiêu đề')}**")
                st.write(f"📅 {event.get('date', 'Chưa đặt ngày')} | ⏰ {event.get('time', 'Chưa đặt giờ')}")
                
                if event.get('description'):
                    st.write(event.get('description', ''))
                
                if event.get('participants'):
                    st.write(f"👥 {', '.join(event.get('participants', []))}")
                
                # Hiển thị người tạo
                if event.get('created_by') and event.get('created_by') in family_data:
                    creator_name = family_data[event.get('created_by')].get("name", "")
                    st.write(f"👤 Tạo bởi: {creator_name}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"Chỉnh sửa", key=f"edit_event_{event_id}"):
                        st.session_state.editing_event = event_id
                with col2:
                    if st.button(f"Xóa", key=f"delete_event_{event_id}"):
                        delete_event(event_id)
                        st.success(f"Đã xóa sự kiện!")
                        st.rerun()
                st.divider()
        
        # Form chỉnh sửa sự kiện (xuất hiện khi đang chỉnh sửa)
        if "editing_event" in st.session_state and st.session_state.editing_event:
            event_id = st.session_state.editing_event
            event = events_data[event_id]
            
            with st.form(f"edit_event_{event_id}"):
                st.write(f"Chỉnh sửa sự kiện: {event['title']}")
                
                # Chuyển đổi định dạng ngày
                try:
                    event_date_obj = datetime.datetime.strptime(event["date"], "%Y-%m-%d").date()
                except:
                    event_date_obj = datetime.date.today()
                
                # Chuyển đổi định dạng giờ
                try:
                    event_time_obj = datetime.datetime.strptime(event["time"], "%H:%M").time()
                except:
                    event_time_obj = datetime.datetime.now().time()
                
                # Các trường chỉnh sửa
                new_title = st.text_input("Tiêu đề", event["title"])
                new_date = st.date_input("Ngày", event_date_obj)
                new_time = st.time_input("Giờ", event_time_obj)
                new_desc = st.text_area("Mô tả", event["description"])
                
                # Multi-select cho người tham gia
                try:
                    member_names = [member.get("name", "") for member_id, member in family_data.items() 
                                   if isinstance(member, dict) and member.get("name")]
                    new_participants = st.multiselect("Người tham gia", member_names, default=event.get("participants", []))
                except Exception as e:
                    st.error(f"Lỗi khi tải danh sách thành viên: {e}")
                    new_participants = []
                
                save_event_edits = st.form_submit_button("Lưu")
                cancel_event_edits = st.form_submit_button("Hủy")
                
                if save_event_edits:
                    events_data[event_id]["title"] = new_title
                    events_data[event_id]["date"] = new_date.strftime("%Y-%m-%d")
                    events_data[event_id]["time"] = new_time.strftime("%H:%M")
                    events_data[event_id]["description"] = new_desc
                    events_data[event_id]["participants"] = new_participants
                    save_data(EVENTS_DATA_FILE, events_data)
                    st.session_state.editing_event = None
                    st.success("Đã cập nhật sự kiện!")
                    st.rerun()
                
                if cancel_event_edits:
                    st.session_state.editing_event = None
                    st.rerun()
        
        st.divider()
        
        # Quản lý ghi chú
        st.write("## Ghi chú")
        
        # Xem ghi chú - lọc theo người dùng hiện tại
        with st.expander("📝 Ghi chú"):
            # Lọc ghi chú theo người dùng hiện tại
            if st.session_state.current_member:
                filtered_notes = {note_id: note for note_id, note in notes_data.items() 
                               if note.get("created_by") == st.session_state.current_member}
            else:
                filtered_notes = notes_data
            
            # Sắp xếp ghi chú theo ngày tạo (với xử lý lỗi)
            try:
                sorted_notes = sorted(
                    filtered_notes.items(),
                    key=lambda x: x[1].get("created_on", ""),
                    reverse=True
                )
            except Exception as e:
                st.error(f"Lỗi khi sắp xếp ghi chú: {e}")
                sorted_notes = []
            
            if not sorted_notes:
                st.write("Không có ghi chú nào")
            
            for note_id, note in sorted_notes:
                st.write(f"**{note.get('title', 'Ghi chú không tiêu đề')}**")
                st.write(note.get('content', ''))
                
                if note.get('tags'):
                    tags = ', '.join([f"#{tag}" for tag in note['tags']])
                    st.write(f"🏷️ {tags}")
                
                # Hiển thị người tạo
                if note.get('created_by') and note.get('created_by') in family_data:
                    creator_name = family_data[note.get('created_by')].get("name", "")
                    st.write(f"👤 Tạo bởi: {creator_name}")
                
                col1, col2 = st.columns(2)
                with col2:
                    if st.button(f"Xóa", key=f"delete_note_{note_id}"):
                        del notes_data[note_id]
                        save_data(NOTES_DATA_FILE, notes_data)
                        st.success(f"Đã xóa ghi chú!")
                        st.rerun()
                st.divider()
        
        st.divider()
        
        # Phần tìm kiếm và truy vấn thông tin thực tế
        with st.expander("🔍 Tìm kiếm thông tin"):
            st.write("**Tìm kiếm thông tin thực tế**")
            
            if not tavily_api_key:
                st.warning("⚠️ Vui lòng nhập Tavily API Key để sử dụng tính năng này.")
            else:
                st.info("✅ Trợ lý sẽ tự động tìm kiếm thông tin khi bạn hỏi về tin tức, thời tiết, thể thao, v.v.")
                
                with st.form("manual_search_form"):
                    search_query = st.text_input("Nhập từ khóa tìm kiếm:")
                    search_button = st.form_submit_button("🔍 Tìm kiếm")
                    
                    if search_button and search_query:
                        with st.spinner("Đang tìm kiếm..."):
                            search_result = search_and_summarize(tavily_api_key, search_query, openai_api_key)
                            st.write("### Kết quả tìm kiếm")
                            st.write(search_result)
        
        # Nút làm mới câu hỏi gợi ý
        if st.button("🔄 Làm mới câu hỏi gợi ý"):
            # Xóa cache để tạo câu hỏi mới
            if "question_cache" in st.session_state:
                st.session_state.question_cache = {}
            st.rerun()
        
        def reset_conversation():
            if "messages" in st.session_state and len(st.session_state.messages) > 0:
                # Trước khi xóa, lưu lịch sử trò chuyện nếu đang trò chuyện với một thành viên
                if st.session_state.current_member and openai_api_key:
                    summary = generate_chat_summary(st.session_state.messages, openai_api_key)
                    save_chat_history(st.session_state.current_member, st.session_state.messages, summary)
                # Xóa tin nhắn
                st.session_state.pop("messages", None)

        st.button(
            "🗑️ Xóa lịch sử trò chuyện", 
            on_click=reset_conversation,
        )

    # --- Nội dung chính ---
    # Kiểm tra nếu người dùng đã nhập OpenAI API Key, nếu không thì hiển thị cảnh báo
    if openai_api_key == "" or openai_api_key is None or "sk-" not in openai_api_key:
        st.write("#")
        st.warning("⬅️ Vui lòng nhập OpenAI API Key để tiếp tục...")
        
        st.write("""
        ### Chào mừng bạn đến với Trợ lý Gia đình!
        
        Ứng dụng này giúp bạn:
        
        - 👨‍👩‍👧‍👦 Lưu trữ thông tin và sở thích của các thành viên trong gia đình
        - 📅 Quản lý các sự kiện gia đình
        - 📝 Tạo và lưu trữ các ghi chú
        - 💬 Trò chuyện với trợ lý AI để cập nhật thông tin
        - 👤 Cá nhân hóa trò chuyện theo từng thành viên
        - 🔍 Tìm kiếm thông tin thời gian thực với Tavily API
        - 📜 Lưu lịch sử trò chuyện và tạo tóm tắt tự động
        
        Để bắt đầu, hãy nhập OpenAI API Key của bạn ở thanh bên trái.
        """)

    else:
        client = OpenAI(api_key=openai_api_key)

        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Hiển thị các tin nhắn trước đó nếu có
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                for content in message["content"]:
                    if content["type"] == "text":
                        st.write(content["text"])
                    elif content["type"] == "image_url":      
                        st.image(content["image_url"]["url"])

        # Hiển thị banner thông tin người dùng hiện tại
        if st.session_state.current_member and st.session_state.current_member in family_data:
            member_name = family_data[st.session_state.current_member].get("name", "")
            st.info(f"👤 Đang trò chuyện với tư cách: **{member_name}**")
        elif st.session_state.current_member is None:
            st.info("👨‍👩‍👧‍👦 Đang trò chuyện trong chế độ chung")
            
        # Hiển thị banner thông tin về tìm kiếm
        if tavily_api_key:
            st.success("🔍 Trợ lý có khả năng tìm kiếm thông tin thời gian thực! Hỏi về tin tức, thể thao, thời tiết, v.v.")
        
        # System prompt cho trợ lý
        system_prompt = f"""
        Bạn là trợ lý gia đình thông minh. Nhiệm vụ của bạn là giúp quản lý thông tin về các thành viên trong gia đình, 
        sở thích của họ, các sự kiện, ghi chú, và phân tích hình ảnh liên quan đến gia đình. Khi người dùng yêu cầu, bạn phải thực hiện ngay các hành động sau:
        
        1. Thêm thông tin về thành viên gia đình (tên, tuổi, sở thích)
        2. Cập nhật sở thích của thành viên gia đình
        3. Thêm, cập nhật, hoặc xóa sự kiện
        4. Thêm ghi chú
        5. Phân tích hình ảnh người dùng đưa ra (món ăn, hoạt động gia đình, v.v.)
        6. Tìm kiếm thông tin thực tế khi được hỏi về tin tức, thời tiết, thể thao, và sự kiện hiện tại
        
        QUAN TRỌNG: Khi cần thực hiện các hành động trên, bạn PHẢI sử dụng đúng cú pháp lệnh đặc biệt này (người dùng sẽ không nhìn thấy):
        
        - Thêm thành viên: ##ADD_FAMILY_MEMBER:{{"name":"Tên","age":"Tuổi","preferences":{{"food":"Món ăn","hobby":"Sở thích","color":"Màu sắc"}}}}##
        - Cập nhật sở thích: ##UPDATE_PREFERENCE:{{"id":"id_thành_viên","key":"loại_sở_thích","value":"giá_trị"}}##
        - Thêm sự kiện: ##ADD_EVENT:{{"title":"Tiêu đề","date":"YYYY-MM-DD","time":"HH:MM","description":"Mô tả","participants":["Tên1","Tên2"]}}##
        - Cập nhật sự kiện: ##UPDATE_EVENT:{{"id":"id_sự_kiện","title":"Tiêu đề mới","date":"YYYY-MM-DD","time":"HH:MM","description":"Mô tả mới","participants":["Tên1","Tên2"]}}##
        - Xóa sự kiện: ##DELETE_EVENT:id_sự_kiện##
        - Thêm ghi chú: ##ADD_NOTE:{{"title":"Tiêu đề","content":"Nội dung","tags":["tag1","tag2"]}}##
        
        QUY TẮC THÊM SỰ KIỆN ĐƠN GIẢN:
        1. Khi được yêu cầu thêm sự kiện, hãy thực hiện NGAY LẬP TỨC mà không cần hỏi thêm thông tin không cần thiết.
        2. Khi người dùng nói "ngày mai" hoặc "tuần sau", hãy tự động tính toán ngày trong cú pháp YYYY-MM-DD.
        3. Nếu không có thời gian cụ thể, sử dụng thời gian mặc định là 19:00.
        4. Sử dụng mô tả ngắn gọn từ yêu cầu của người dùng.
        5. Chỉ hỏi thông tin nếu thực sự cần thiết, tránh nhiều bước xác nhận.
        6. Sau khi thêm/cập nhật/xóa sự kiện, tóm tắt ngắn gọn hành động đã thực hiện.
        
        TÌM KIẾM THÔNG TIN THỜI GIAN THỰC:
        1. Khi người dùng hỏi về tin tức, thời tiết, thể thao, sự kiện hiện tại, thông tin sản phẩm mới, hoặc bất kỳ dữ liệu cập nhật nào, hệ thống đã tự động tìm kiếm thông tin thực tế cho bạn.
        2. Hãy sử dụng thông tin tìm kiếm này để trả lời người dùng một cách chính xác và đầy đủ.
        3. Luôn đề cập đến nguồn thông tin khi sử dụng kết quả tìm kiếm.
        4. Nếu không có thông tin tìm kiếm, hãy trả lời dựa trên kiến thức của bạn và lưu ý rằng thông tin có thể không cập nhật.
        
        Hôm nay là {datetime.datetime.now().strftime("%d/%m/%Y")}.
        
        CẤU TRÚC JSON PHẢI CHÍNH XÁC như trên. Đảm bảo dùng dấu ngoặc kép cho cả keys và values. Đảm bảo các dấu ngoặc nhọn và vuông được đóng đúng cách.
        
        QUAN TRỌNG: Khi người dùng yêu cầu tạo sự kiện mới, hãy luôn sử dụng lệnh ##ADD_EVENT:...## trong phản hồi của bạn mà không cần quá nhiều bước xác nhận.
        
        Đối với hình ảnh:
        - Nếu người dùng gửi hình ảnh món ăn, hãy mô tả món ăn, và đề xuất cách nấu hoặc thông tin dinh dưỡng nếu phù hợp
        - Nếu là hình ảnh hoạt động gia đình, hãy mô tả hoạt động và đề xuất cách ghi nhớ khoảnh khắc đó
        - Với bất kỳ hình ảnh nào, hãy giúp người dùng liên kết nó với thành viên gia đình hoặc sự kiện nếu phù hợp
        """
        
        # Thêm thông tin về người dùng hiện tại
        if st.session_state.current_member and st.session_state.current_member in family_data:
            current_member = family_data[st.session_state.current_member]
            system_prompt += f"""
            THÔNG TIN NGƯỜI DÙNG HIỆN TẠI:
            Bạn đang trò chuyện với: {current_member.get('name')}
            Tuổi: {current_member.get('age', '')}
            Sở thích: {json.dumps(current_member.get('preferences', {}), ensure_ascii=False)}
            
            QUAN TRỌNG: Hãy điều chỉnh cách giao tiếp và đề xuất phù hợp với người dùng này. Các sự kiện và ghi chú sẽ được ghi danh nghĩa người này tạo.
            """
        
        # Thêm thông tin dữ liệu
        system_prompt += f"""
        Thông tin hiện tại về gia đình:
        {json.dumps(family_data, ensure_ascii=False, indent=2)}
        
        Sự kiện sắp tới:
        {json.dumps(events_data, ensure_ascii=False, indent=2)}
        
        Ghi chú:
        {json.dumps(notes_data, ensure_ascii=False, indent=2)}
        
        Hãy hiểu và đáp ứng nhu cầu của người dùng một cách tự nhiên và hữu ích. Không hiển thị các lệnh đặc biệt
        trong phản hồi của bạn, chỉ sử dụng chúng để thực hiện các hành động được yêu cầu.
        """
        
        # Kiểm tra và xử lý câu hỏi gợi ý đã chọn
        if st.session_state.process_suggested and st.session_state.suggested_question:
            question = st.session_state.suggested_question
            st.session_state.suggested_question = None
            st.session_state.process_suggested = False
            
            # Thêm câu hỏi vào messages
            st.session_state.messages.append(
                {
                    "role": "user", 
                    "content": [{
                        "type": "text",
                        "text": question,
                    }]
                }
            )
            
            # Hiển thị tin nhắn người dùng
            with st.chat_message("user"):
                st.markdown(question)
            
            # Xử lý phản hồi từ trợ lý
            with st.chat_message("assistant"):
                st.write_stream(stream_llm_response(
                    api_key=openai_api_key, 
                    system_prompt=system_prompt,
                    current_member=st.session_state.current_member
                ))
            
            # Rerun để cập nhật giao diện và tránh xử lý trùng lặp
            st.rerun()
        
        # Hiển thị câu hỏi gợi ý
        if openai_api_key:
            # Container cho câu hỏi gợi ý với CSS tùy chỉnh
            st.markdown("""
            <style>
            .suggestion-container {
                margin-top: 20px;
                margin-bottom: 20px;
            }
            .suggestion-title {
                font-size: 16px;
                font-weight: 500;
                margin-bottom: 10px;
                color: #555;
            }
            .suggestion-box {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-bottom: 15px;
            }
            </style>
            """, unsafe_allow_html=True)
            
            st.markdown('<div class="suggestion-container">', unsafe_allow_html=True)
            st.markdown('<div class="suggestion-title">💡 Câu hỏi gợi ý cho bạn:</div>', unsafe_allow_html=True)
            
            # Tạo câu hỏi gợi ý động
            suggested_questions = generate_dynamic_suggested_questions(
                api_key=openai_api_key,
                member_id=st.session_state.current_member,
                max_questions=5
            )
            
            # Hiển thị các nút cho câu hỏi gợi ý
            st.markdown('<div class="suggestion-box">', unsafe_allow_html=True)
            
            # Chia câu hỏi thành 2 dòng
            row1, row2 = st.columns([1, 1])
            
            with row1:
                for i, question in enumerate(suggested_questions[:3]):
                    if st.button(
                        question,
                        key=f"suggest_q_{i}",
                        use_container_width=True
                    ):
                        handle_suggested_question(question)
            
            with row2:
                for i, question in enumerate(suggested_questions[3:], 3):
                    if st.button(
                        question,
                        key=f"suggest_q_{i}",
                        use_container_width=True
                    ):
                        handle_suggested_question(question)
            
            st.markdown('</div></div>', unsafe_allow_html=True)

        # Thêm chức năng hình ảnh
        with st.sidebar:
            st.divider()
            st.write("## 🖼️ Hình ảnh")
            st.write("Thêm hình ảnh để hỏi trợ lý về món ăn, hoạt động gia đình...")

            def add_image_to_messages():
                if st.session_state.uploaded_img or ("camera_img" in st.session_state and st.session_state.camera_img):
                    img_type = st.session_state.uploaded_img.type if st.session_state.uploaded_img else "image/jpeg"
                    raw_img = Image.open(st.session_state.uploaded_img or st.session_state.camera_img)
                    img = get_image_base64(raw_img)
                    st.session_state.messages.append(
                        {
                            "role": "user", 
                            "content": [{
                                "type": "image_url",
                                "image_url": {"url": f"data:{img_type};base64,{img}"}
                            }]
                        }
                    )
                    st.rerun()
            
            cols_img = st.columns(2)
            with cols_img[0]:
                with st.popover("📁 Tải lên"):
                    st.file_uploader(
                        "Tải lên hình ảnh:", 
                        type=["png", "jpg", "jpeg"],
                        accept_multiple_files=False,
                        key="uploaded_img",
                        on_change=add_image_to_messages,
                    )

            with cols_img[1]:                    
                with st.popover("📸 Camera"):
                    activate_camera = st.checkbox("Bật camera")
                    if activate_camera:
                        st.camera_input(
                            "Chụp ảnh", 
                            key="camera_img",
                            on_change=add_image_to_messages,
                        )

        # Chat input và các tùy chọn âm thanh
        audio_prompt = None
        if "prev_speech_hash" not in st.session_state:
            st.session_state.prev_speech_hash = None

        # Ghi âm
        st.write("🎤 Bạn có thể nói:")
        speech_input = audio_recorder("Nhấn để nói", icon_size="2x", neutral_color="#6ca395")
        if speech_input and st.session_state.prev_speech_hash != hash(speech_input):
            st.session_state.prev_speech_hash = hash(speech_input)
            
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=("audio.wav", speech_input),
            )

            audio_prompt = transcript.text

        # Chat input
        if prompt := st.chat_input("Xin chào! Tôi có thể giúp gì cho gia đình bạn?") or audio_prompt:
            st.session_state.messages.append(
                {
                    "role": "user", 
                    "content": [{
                        "type": "text",
                        "text": prompt or audio_prompt,
                    }]
                }
            )
            
            # Hiển thị tin nhắn mới
            with st.chat_message("user"):
                st.markdown(prompt or audio_prompt)

            with st.chat_message("assistant"):
                st.write_stream(stream_llm_response(
                    api_key=openai_api_key, 
                    system_prompt=system_prompt,
                    current_member=st.session_state.current_member
                ))

if __name__=="__main__":
    main()