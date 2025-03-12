import streamlit as st
from openai import OpenAI
import dotenv
import os
from PIL import Image
from audio_recorder_streamlit import audio_recorder
import base64
from io import BytesIO
import json
import os.path

# Tải biến môi trường từ file .env (nếu có)
dotenv.load_dotenv()

# Chỉ sử dụng model GPT-4o-mini
MODEL_NAME = "gpt-4o-mini"

# Đường dẫn file lưu trữ dữ liệu
DATA_FILE = "family_data.json"

# Hàm lưu dữ liệu gia đình
def save_family_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Hàm tải dữ liệu gia đình
def load_family_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        # Tạo dữ liệu mẫu nếu chưa có file
        default_data = {
            "members": [
                {
                    "name": "Bố",
                    "interests": ["thể thao", "tin tức", "đầu tư"],
                    "dob": "",
                    "notes": ""
                },
                {
                    "name": "Mẹ",
                    "interests": ["nấu ăn", "làm vườn", "sách"],
                    "dob": "",
                    "notes": ""
                }
            ],
            "family_info": {
                "address": "",
                "important_dates": [],
                "shared_interests": ["du lịch", "ăn uống"]
            }
        }
        save_family_data(default_data)
        return default_data

# Tạo gợi ý câu hỏi dựa trên sở thích
def generate_question_suggestions(member, client=None):
    suggestions = []
    
    # Nếu không có thông tin thành viên, trả về câu hỏi mặc định
    if not member or "interests" not in member or not member["interests"]:
        return [
            "Bạn muốn biết thêm thông tin gì hôm nay?",
            "Có vấn đề gì tôi có thể giúp đỡ?",
            "Bạn có dự định gì cho ngày hôm nay?",
            "Bạn muốn tìm hiểu về chủ đề nào?",
            "Có hoạt động gia đình nào bạn đang lên kế hoạch?",
            "Bạn đang quan tâm đến vấn đề gì?",
            "Bạn muốn tôi gợi ý món ăn, hoạt động hay thông tin gì?",
            "Có chủ đề cụ thể nào bạn muốn thảo luận hôm nay?"
        ]
    
    # Nếu có API client, tạo câu hỏi động từ GPT
    if client:
        try:
            interests_str = ", ".join(member["interests"])
            prompt = f"""
            Tạo 5 câu hỏi gợi ý đa dạng cho người dùng có tên "{member['name']}" với các sở thích: {interests_str}.
            Câu hỏi nên thú vị, phù hợp với thời điểm hiện tại, và kích thích cuộc trò chuyện.
            Đảm bảo câu hỏi đa dạng và không lặp lại.
            Chỉ trả về danh sách câu hỏi, mỗi câu một dòng, không có số thứ tự hay dấu gạch đầu dòng.
            """
            
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "Bạn là một trợ lý giúp tạo câu hỏi gợi ý dựa trên sở thích của người dùng."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=512
            )
            
            # Tách các câu hỏi từ phản hồi
            generated_questions = response.choices[0].message.content.strip().split('\n')
            # Lọc các dòng trống và loại bỏ dấu gạch đầu dòng hoặc số nếu có
            suggestions = [q.strip().replace('- ', '').replace('* ', '') for q in generated_questions if q.strip()]
            
            # Đảm bảo có ít nhất 5 câu hỏi
            if len(suggestions) < 5:
                remaining = 5 - len(suggestions)
                suggestions.extend(create_fallback_questions(member, remaining))
                
            return suggestions[:5]
            
        except Exception as e:
            print(f"Lỗi khi tạo câu hỏi động: {e}")
            # Nếu có lỗi, sử dụng phương pháp fallback
            
    # Phương pháp dự phòng - tạo câu hỏi dựa trên sở thích
    return create_fallback_questions(member, 5)

# Hàm tạo câu hỏi dự phòng khi không thể sử dụng API
def create_fallback_questions(member, count=5):
    suggestions = []
    common_questions = {
        "thể thao": [
            "Kết quả cúp châu Âu hôm nay là gì?",
            "Thông tin mới nhất về chuyển nhượng cầu thủ?",
            "Lịch thi đấu bóng đá trong tuần này?",
            "Bảng xếp hạng Ngoại hạng Anh hiện tại?",
            "Ai đang dẫn đầu giải Grand Slam tennis năm nay?",
            "Kết quả trận đấu giữa đội tuyển Việt Nam?"
        ],
        "nấu ăn": [
            "Công thức làm bánh mì homemade?",
            "Cách nấu phở bò truyền thống?",
            "Bí quyết làm sushi tại nhà?",
            "Công thức làm bánh trung thu nhân thập cẩm?",
            "Menu đồ ăn healthy trong 7 ngày?"
        ],
        "đọc sách": [
            "Top 10 sách bán chạy nhất tháng này?",
            "Sách mới của tác giả Nguyễn Nhật Ánh?",
            "Tóm tắt tiểu thuyết 'Trăm năm cô đơn'?",
            "Những cuốn sách về tài chính cá nhân hay nhất?"
        ],
        "du lịch": [
            "Chi phí du lịch Đà Nẵng 3 ngày 2 đêm?",
            "Thời tiết ở Đà Lạt tháng này thế nào?",
            "Kinh nghiệm du lịch Phú Quốc tự túc?",
            "Những địa điểm du lịch mới nổi ở Việt Nam?"
        ],
        "âm nhạc": [
            "Album mới nhất của Sơn Tùng MTP?",
            "Lịch concert của các nghệ sĩ tại Việt Nam?",
            "Top 10 bài hát đang thịnh hành trên Spotify?",
            "Thông tin về giải thưởng Grammy năm nay?"
        ],
        "công nghệ": [
            "So sánh iPhone 15 Pro và Samsung S24 Ultra?",
            "Mẫu laptop mới nhất của Apple?",
            "Thông tin về công nghệ AI trong y tế?",
            "Cách bảo vệ dữ liệu cá nhân trên điện thoại?"
        ],
        "làm vườn": [
            "Cách trồng rau sạch trong nhà phố?",
            "Loại cây cảnh dễ chăm sóc trong nhà?",
            "Cách xử lý sâu bệnh trên cây hoa hồng?",
            "Lịch trồng rau theo mùa tại Việt Nam?"
        ],
        "phim ảnh": [
            "Phim Việt Nam mới ra rạp tháng này?",
            "Top phim Netflix đang hot?",
            "Lịch chiếu phim Marvel sắp tới?",
            "Đánh giá về phim 'Nhà bà Nữ'?"
        ],
        "giáo dục": [
            "Lịch thi tốt nghiệp THPT năm nay?",
            "Thông tin về các trường đại học top đầu Việt Nam?",
            "Kinh nghiệm ôn thi đại học hiệu quả?",
            "Các khóa học online chất lượng về lập trình?"
        ],
        "sức khỏe": [
            "Cách phòng tránh bệnh cúm mùa?",
            "Lịch tiêm vaccine cho trẻ em?",
            "Chế độ ăn giảm cân khoa học?",
            "Cách chăm sóc người già trong mùa lạnh?"
        ]
    }
    
    # Câu hỏi liên quan đến thông tin thời sự và cập nhật
    general_info_questions = [
        "Tin tức nổi bật trong nước hôm nay?",
        "Giá vàng hiện tại như thế nào?",
        "Tỷ giá USD/VND hôm nay?",
        "Dự báo thời tiết cuối tuần này?",
        "Tình hình giao thông tại Hà Nội/TP.HCM?",
        "Lịch cắt điện trong khu vực hôm nay?",
        "Kết quả xổ số miền Bắc/Trung/Nam hôm qua?",
        "Thông tin về chính sách mới của chính phủ?",
        "Giá xăng dầu mới nhất?",
        "Lịch nghỉ lễ tết sắp tới?"
    ]
    
    # Lấy câu hỏi dựa trên sở thích
    for interest in member["interests"]:
        interest_lower = interest.lower()
        # Tìm chủ đề gần nhất trong danh sách common_questions
        matched_topic = None
        for topic in common_questions:
            if topic in interest_lower or interest_lower in topic:
                matched_topic = topic
                break
        
        # Nếu tìm thấy chủ đề phù hợp, thêm câu hỏi liên quan
        if matched_topic:
            suggestions.extend(common_questions[matched_topic])
        else:
            # Nếu không tìm thấy, tạo câu hỏi chung cho sở thích đó
            suggestions.append(f"Thông tin mới nhất về {interest}?")
            suggestions.append(f"Top 5 sự kiện liên quan đến {interest} gần đây?")
    
    # Bổ sung thêm câu hỏi thông tin chung
    import random
    random.shuffle(general_info_questions)
    suggestions.extend(general_info_questions)
    
    # Loại bỏ trùng lặp và giới hạn số lượng
    unique_suggestions = []
    for s in suggestions:
        if s not in unique_suggestions:
            unique_suggestions.append(s)
    
    # Xáo trộn để có sự đa dạng
    random.shuffle(unique_suggestions)
    
    return unique_suggestions[:count]

# Hàm tạo tin nhắn hệ thống cho AI
def create_system_message(member):
    if not member:
        return "Bạn là trợ lý gia đình thông minh, giúp đỡ mọi thành viên trong gia đình với các vấn đề hàng ngày."
    
    interests_str = ", ".join(member["interests"]) if "interests" in member else "chưa có thông tin"
    
    return f"""Bạn là trợ lý gia đình thông minh đang nói chuyện với {member['name']}. 
Sở thích của họ bao gồm: {interests_str}.
Hãy cá nhân hóa câu trả lời phù hợp với sở thích và nhu cầu của họ.
Trả lời một cách thân thiện, hữu ích và tôn trọng.
"""

# Hàm chuyển đổi file thành base64
def get_image_base64(image_raw):
    buffered = BytesIO()
    image_raw.save(buffered, format=image_raw.format)
    img_byte = buffered.getvalue()
    return base64.b64encode(img_byte).decode('utf-8')

# Hàm gửi tin nhắn và nhận phản hồi từ AI
def stream_llm_response(api_key, member):
    # Cập nhật cache ngày hôm nay để AI biết ngày hiện tại
    from datetime import datetime
    today = datetime.now().strftime("%d/%m/%Y")
    day_of_week = datetime.now().strftime("%A")
    
    # Tạo tin nhắn hệ thống với thông tin cá nhân hóa và ngày hiện tại
    system_message = create_system_message(member)
    system_message += f"\nHôm nay là {day_of_week}, ngày {today}."
    
    messages = [{"role": "system", "content": system_message}] + st.session_state.messages
    
    client = OpenAI(api_key=api_key)
    response_message = ""
    
    for chunk in client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0.7,
        max_tokens=2048,
        stream=True,
    ):
        chunk_text = chunk.choices[0].delta.content or ""
        response_message += chunk_text
        yield chunk_text

    st.session_state.messages.append({
        "role": "assistant", 
        "content": response_message
    })

def main():
    # --- Cấu hình trang ---
    st.set_page_config(
        page_title="Trợ lý Gia đình",
        page_icon="👪",
        layout="centered",
        initial_sidebar_state="expanded",
    )
    
    # Thiết lập CSS tùy chỉnh
    st.markdown("""
    <style>
    .stButton button {
        background-color: #f0f2f6;
        border-radius: 20px;
        transition: all 0.3s;
    }
    .stButton button:hover {
        background-color: #e0e2e6;
        transform: translateY(-2px);
    }
    div[data-testid="column"] > div.stButton > button {
        min-height: 60px;
        white-space: normal !important;
        word-wrap: break-word;
        height: auto;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        display: flex;
    }
    </style>
    """, unsafe_allow_html=True)

    # --- Tiêu đề ---
    st.markdown("<h1 style='text-align: center; color: #6ca395;'>👪 <i>Trợ lý Gia đình</i> 💬</h1>", unsafe_allow_html=True)
    
    # Tải dữ liệu gia đình
    if "family_data" not in st.session_state:
        st.session_state.family_data = load_family_data()
    
    # Khởi tạo biến session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "current_member" not in st.session_state:
        st.session_state.current_member = None

    # --- Thanh bên (Sidebar) ---
    with st.sidebar:
        cols_keys = st.columns(1)
        with cols_keys[0]:
            default_openai_api_key = os.getenv("OPENAI_API_KEY") or ""
            with st.popover("🔐 OpenAI API Key"):
                openai_api_key = st.text_input("Nhập OpenAI API Key của bạn", 
                                              value=default_openai_api_key, 
                                              type="password")
        
        st.divider()
        
        # Quản lý thành viên gia đình
        st.subheader("👨‍👩‍👧‍👦 Thành viên gia đình")
        
        # Chọn thành viên
        member_names = [member["name"] for member in st.session_state.family_data["members"]]
        selected_member = st.selectbox("Chọn thành viên", 
                                      options=member_names,
                                      index=0 if member_names else None)
        
        # Cập nhật thành viên hiện tại
        if selected_member:
            for member in st.session_state.family_data["members"]:
                if member["name"] == selected_member:
                    st.session_state.current_member = member
                    break
        
        # Thêm thành viên mới
        with st.expander("➕ Thêm thành viên mới"):
            new_name = st.text_input("Tên thành viên")
            new_interests = st.text_area("Sở thích (mỗi sở thích một dòng)")
            new_dob = st.date_input("Ngày sinh", value=None)
            new_notes = st.text_area("Ghi chú")
            
            if st.button("Thêm"):
                if new_name:
                    interests_list = [interest.strip() for interest in new_interests.split("\n") if interest.strip()]
                    new_member = {
                        "name": new_name,
                        "interests": interests_list,
                        "dob": str(new_dob) if new_dob else "",
                        "notes": new_notes
                    }
                    st.session_state.family_data["members"].append(new_member)
                    save_family_data(st.session_state.family_data)
                    st.success(f"Đã thêm thành viên: {new_name}")
                    st.experimental_rerun()
                else:
                    st.error("Vui lòng nhập tên thành viên")
        
        # Chỉnh sửa thành viên
        if st.session_state.current_member:
            with st.expander("✏️ Chỉnh sửa thông tin"):
                member = st.session_state.current_member
                edit_interests = st.text_area(
                    "Sở thích (mỗi sở thích một dòng)", 
                    value="\n".join(member["interests"]) if "interests" in member else "",
                    key=f"edit_interests_{member['name']}"
                )
                edit_notes = st.text_area(
                    "Ghi chú", 
                    value=member.get("notes", ""),
                    key=f"edit_notes_{member['name']}"
                )
                
                if st.button("Cập nhật", key=f"update_btn_{member['name']}"):
                    for m in st.session_state.family_data["members"]:
                        if m["name"] == member["name"]:
                            m["interests"] = [interest.strip() for interest in edit_interests.split("\n") if interest.strip()]
                            m["notes"] = edit_notes
                            st.session_state.current_member = m
                            break
                    
                    save_family_data(st.session_state.family_data)
                    st.success("Đã cập nhật thông tin")
                    st.experimental_rerun()
                
                if st.button("Xóa thành viên", key=f"delete_btn_{member['name']}", type="primary", use_container_width=True):
                    st.session_state.family_data["members"] = [
                        m for m in st.session_state.family_data["members"] 
                        if m["name"] != member["name"]
                    ]
                    
                    save_family_data(st.session_state.family_data)
                    st.session_state.current_member = None
                    st.success(f"Đã xóa thành viên: {member['name']}")
                    st.experimental_rerun()
        
        st.divider()
        
        # Reset cuộc trò chuyện
        def reset_conversation():
            if "messages" in st.session_state:
                st.session_state.messages = []
            if "question_suggestions" in st.session_state:
                st.session_state.pop("question_suggestions")
        
        st.button("🗑️ Xóa cuộc hội thoại", on_click=reset_conversation, key="reset_conversation_btn")

    # --- Kiểm tra API Key ---
    if openai_api_key == "" or openai_api_key is None or "sk-" not in openai_api_key:
        st.warning("⬅️ Vui lòng nhập OpenAI API Key để tiếp tục...")
        st.info("Bạn cần có API key của OpenAI để sử dụng ứng dụng này. Đăng ký tại https://platform.openai.com")
        return

    # --- Hiển thị tin nhắn trước đó ---
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # --- Hiển thị thông tin thành viên hiện tại ---
    if st.session_state.current_member:
        member = st.session_state.current_member
        with st.expander(f"ℹ️ Thông tin của {member['name']}", expanded=False):
            st.write(f"**Sở thích:** {', '.join(member['interests']) if 'interests' in member else 'Chưa có thông tin'}")
            if member.get("dob"):
                st.write(f"**Ngày sinh:** {member['dob']}")
            if member.get("notes"):
                st.write(f"**Ghi chú:** {member['notes']}")
    
    # --- Hiển thị gợi ý câu hỏi và nút làm mới ---
    if st.session_state.current_member:
        # Lưu trữ gợi ý trong session_state để có thể làm mới
        if "question_suggestions" not in st.session_state:
            client = OpenAI(api_key=openai_api_key) if openai_api_key else None
            st.session_state.question_suggestions = generate_question_suggestions(
                st.session_state.current_member, 
                client
            )
        
        # Hiển thị nút làm mới gợi ý
        refresh_col, title_col = st.columns([1, 9])
        with refresh_col:
            if st.button("🔄", key="refresh_suggestions", help="Làm mới gợi ý câu hỏi"):
                client = OpenAI(api_key=openai_api_key) if openai_api_key else None
                st.session_state.question_suggestions = generate_question_suggestions(
                    st.session_state.current_member, 
                    client
                )
        
        with title_col:
            st.markdown("### Gợi ý câu hỏi")
        
        # Hiển thị các gợi ý
        suggestions = st.session_state.question_suggestions
        
        # Tính số cột tối đa (trên thiết bị nhỏ không thể hiện quá nhiều cột)
        max_cols = min(len(suggestions), 3)
        # Tạo các hàng cho gợi ý
        for i in range(0, len(suggestions), max_cols):
            # Lấy số lượng cột cho hàng hiện tại (có thể ít hơn max_cols ở hàng cuối)
            num_cols = min(max_cols, len(suggestions) - i)
            cols = st.columns(num_cols)
            
            for j in range(num_cols):
                idx = i + j
                suggestion = suggestions[idx]
                if cols[j].button(suggestion, key=f"suggestion_{idx}", use_container_width=True):
                    # Thêm câu hỏi được chọn vào tin nhắn
                    st.session_state.messages.append({"role": "user", "content": suggestion})
                    
                    # Hiển thị tin nhắn người dùng
                    with st.chat_message("user"):
                        st.write(suggestion)
                    
                    # Hiển thị phản hồi của AI
                    with st.chat_message("assistant"):
                        st.write_stream(stream_llm_response(
                            api_key=openai_api_key,
                            member=st.session_state.current_member
                        ))
                    
                    # Buộc trang làm mới để hiển thị đúng
                    st.experimental_rerun()

    # --- Chức năng ghi âm ---
    st.divider()
    st.write("🎤 **Nói chuyện với trợ lý:**")
    speech_input = audio_recorder("Nhấn để nói", icon_size="2x", neutral_color="#6ca395")

    audio_prompt = None    
    if speech_input:
        if "prev_speech_hash" not in st.session_state:
            st.session_state.prev_speech_hash = None
            
        if st.session_state.prev_speech_hash != hash(speech_input):
            st.session_state.prev_speech_hash = hash(speech_input)
            
            # Sử dụng OpenAI Whisper để chuyển giọng nói thành văn bản
            client = OpenAI(api_key=openai_api_key)
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=("audio.wav", speech_input),
            )
            
            audio_prompt = transcript.text
            
            if audio_prompt:
                # Thêm tin nhắn vào lịch sử
                st.session_state.messages.append({"role": "user", "content": audio_prompt})
                
                # Hiển thị tin nhắn người dùng
                with st.chat_message("user"):
                    st.write(audio_prompt)
                
                # Hiển thị phản hồi của AI
                with st.chat_message("assistant"):
                    st.write_stream(stream_llm_response(
                        api_key=openai_api_key,
                        member=st.session_state.current_member
                    ))
                
                st.experimental_rerun()

    # --- Chat input ---
    if prompt := st.chat_input("Xin chào! Tôi có thể giúp gì cho bạn?"):
        # Thêm tin nhắn vào lịch sử
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Hiển thị tin nhắn người dùng
        with st.chat_message("user"):
            st.write(prompt)
        
        # Hiển thị phản hồi của AI
        with st.chat_message("assistant"):
            st.write_stream(stream_llm_response(
                api_key=openai_api_key,
                member=st.session_state.current_member
            ))

if __name__=="__main__":
    main()