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
    
    # Nếu không có thông tin thành viên, trả về câu hỏi thông tin mặc định
    if not member or "interests" not in member or not member["interests"]:
        return [
            "Thời tiết hôm nay",
            "Tin tức nổi bật trong ngày",
            "Kết quả bóng đá mới nhất",
            "Giá vàng hiện tại",
            "Phim mới chiếu rạp tuần này", 
            "Top 10 bài hát thịnh hành",
            "Công thức nấu ăn đơn giản",
            "Sự kiện cuối tuần tại địa phương"
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
    information_questions = {
        "thể thao": [
            "Kết quả cúp châu Âu hôm nay",
            "Thông tin mới nhất về giải Ngoại hạng Anh",
            "Lịch thi đấu bóng đá tuần này",
            "Bảng xếp hạng La Liga hiện tại",
            "Chuyển nhượng cầu thủ mới nhất"
        ],
        "nấu ăn": [
            "Công thức làm bánh chocolate",
            "Cách làm món phở gà truyền thống",
            "Top 5 món ăn dễ làm cho bữa tối",
            "Món tráng miệng từ trái cây mùa hè",
            "Công thức nấu lẩu Thái chua cay"
        ],
        "đọc sách": [
            "Top sách bán chạy tháng này",
            "Thông tin về tác giả Haruki Murakami",
            "Giới thiệu tiểu thuyết mới xuất bản",
            "Sách hay về phát triển bản thân",
            "Tóm tắt tiểu thuyết nổi tiếng"
        ],
        "du lịch": [
            "Điểm đến du lịch nổi tiếng ở Việt Nam",
            "Kinh nghiệm du lịch tiết kiệm cho gia đình",
            "Thông tin về visa du lịch Nhật Bản",
            "Giá vé máy bay đi châu Âu mùa này",
            "Các resort tốt nhất cho gia đình có trẻ nhỏ"
        ],
        "âm nhạc": [
            "Top 10 bài hát đang thịnh hành",
            "Thông tin về concert sắp diễn ra",
            "Album mới ra mắt tháng này",
            "Tiểu sử ca sĩ nổi tiếng",
            "Lịch biểu diễn nhạc sống cuối tuần này"
        ],
        "công nghệ": [
            "Thông tin về iPhone mới nhất",
            "So sánh các mẫu laptop gaming",
            "Tin tức mới về trí tuệ nhân tạo",
            "Đánh giá tai nghe không dây tốt nhất",
            "Bảng giá điện thoại Android cao cấp"
        ],
        "làm vườn": [
            "Cách trồng cây ăn quả trong chậu",
            "Hướng dẫn chăm sóc cây cảnh trong nhà",
            "Thông tin về phân bón hữu cơ tốt nhất",
            "Lịch trồng rau theo mùa",
            "Cách phòng trừ sâu bệnh tự nhiên"
        ],
        "tài chính": [
            "Tỷ giá ngoại tệ hôm nay",
            "Cập nhật giá vàng mới nhất",
            "Dự báo thị trường chứng khoán tuần tới",
            "So sánh lãi suất ngân hàng hiện tại",
            "Hướng dẫn đầu tư cho người mới bắt đầu"
        ],
        "giáo dục": [
            "Thông tin tuyển sinh đại học năm nay",
            "Các khóa học online được đánh giá cao",
            "Danh sách học bổng cho học sinh THPT",
            "Lịch thi IELTS/TOEFL trong tháng",
            "So sánh các phương pháp giáo dục trẻ em"
        ],
        "phim ảnh": [
            "Phim mới chiếu rạp tuần này",
            "Đánh giá phim bom tấn mới nhất",
            "Lịch phát sóng series nổi tiếng",
            "Thông tin về đề cử giải Oscar",
            "Phim hay trên Netflix tháng này"
        ]
    }
    
    # Câu hỏi thông tin chung
    general_info_questions = [
        "Dự báo thời tiết cuối tuần này",
        "Tin tức nổi bật trong ngày",
        "Sự kiện văn hóa sắp diễn ra",
        "Thông tin về dịch vụ y tế gần đây",
        "Giá cả thực phẩm thị trường hiện nay",
        "Thông tin giao thông giờ cao điểm",
        "Tổng hợp sự kiện cuối tuần tại địa phương",
        "Lịch nghỉ lễ sắp tới",
        "Thông tin về các hoạt động cho trẻ em",
        "Khuyến mãi mua sắm đang diễn ra"
    ]
    
    # Lấy câu hỏi dựa trên sở thích
    for interest in member["interests"]:
        interest_lower = interest.lower()
        # Tìm chủ đề gần nhất trong danh sách thông tin
        matched_topic = None
        for topic in information_questions:
            if topic in interest_lower or interest_lower in topic:
                matched_topic = topic
                break
        
        # Nếu tìm thấy chủ đề phù hợp, thêm câu hỏi liên quan
        if matched_topic:
            suggestions.extend(information_questions[matched_topic])
        else:
            # Nếu không tìm thấy, tạo câu hỏi thông tin chung cho sở thích đó
            suggestions.append(f"Thông tin mới nhất về {interest}")
            suggestions.append(f"Top 5 điều thú vị về {interest}")
    
    # Bổ sung thêm câu hỏi thông tin chung nếu cần
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
def stream_llm_response(api_key, member, include_image=False, image_url=None):
    # Cập nhật cache ngày hôm nay để AI biết ngày hiện tại
    from datetime import datetime
    today = datetime.now().strftime("%d/%m/%Y")
    day_of_week = datetime.now().strftime("%A")
    
    # Tạo tin nhắn hệ thống với thông tin cá nhân hóa và ngày hiện tại
    system_message = create_system_message(member)
    system_message += f"\nHôm nay là {day_of_week}, ngày {today}."
    
    # Sao chép tin nhắn để không ảnh hưởng đến session_state
    messages = [{"role": "system", "content": system_message}]
    
    # Thêm hình ảnh vào cuối chuỗi tin nhắn nếu có
    if include_image and image_url:
        # Thêm tin nhắn cuối cùng từ người dùng nếu có
        if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
            last_user_message = st.session_state.messages[-1]["content"]
            messages.append({"role": "user", "content": last_user_message})
        
        # Thêm hình ảnh
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": "Phân tích hình ảnh này:"},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        })
    else:
        # Thêm tất cả tin nhắn hiện có
        messages.extend(st.session_state.messages)
    
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

    # Chỉ lưu phản hồi vào lịch sử khi không phải xử lý hình ảnh riêng
    if not include_image or not image_url:
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
    .media-tools {
        border: 1px solid #f0f2f6;
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 10px;
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
        
    if "show_image_analysis" not in st.session_state:
        st.session_state.show_image_analysis = False
        
    if "image_url" not in st.session_state:
        st.session_state.image_url = None

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

    # --- Sidebar ---
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
                    # Khi đổi thành viên, làm mới gợi ý câu hỏi
                    if "question_suggestions" in st.session_state:
                        st.session_state.pop("question_suggestions")
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