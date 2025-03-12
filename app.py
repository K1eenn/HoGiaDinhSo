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
def generate_question_suggestions(member):
    suggestions = []
    
    if member and "interests" in member:
        for interest in member["interests"]:
            if interest == "thể thao":
                suggestions.append("Có tin tức gì mới về bóng đá không?")
                suggestions.append("Gợi ý một số bài tập thể dục tại nhà?")
            elif interest == "nấu ăn":
                suggestions.append("Món ăn nào dễ làm cho bữa tối hôm nay?")
                suggestions.append("Công thức làm bánh chocolate đơn giản?")
            elif interest == "đầu tư":
                suggestions.append("Các hình thức đầu tư an toàn cho người mới?")
                suggestions.append("Tư vấn về quản lý tài chính gia đình?")
            elif interest == "làm vườn":
                suggestions.append("Cách chăm sóc cây trong nhà vào mùa đông?")
                suggestions.append("Loại rau nào dễ trồng trong chậu tại nhà?")
            elif interest == "sách":
                suggestions.append("Gợi ý một số sách hay về chủ đề phát triển bản thân?")
                suggestions.append("Có tiểu thuyết mới nào đáng đọc không?")
            elif interest == "du lịch":
                suggestions.append("Những địa điểm du lịch gia đình phù hợp với trẻ em?")
                suggestions.append("Mẹo tiết kiệm chi phí khi đi du lịch gia đình?")
            else:
                suggestions.append(f"Chia sẻ thông tin thú vị về {interest}?")
    
    # Thêm các câu hỏi chung
    suggestions.append("Gợi ý hoạt động gia đình cho cuối tuần này?")
    suggestions.append("Lời khuyên về cân bằng công việc và thời gian cho gia đình?")
    
    return suggestions[:5]  # Giới hạn 5 gợi ý

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
    system_message = create_system_message(member)
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
                    value="\n".join(member["interests"]) if "interests" in member else ""
                )
                edit_notes = st.text_area("Ghi chú", value=member.get("notes", ""))
                
                if st.button("Cập nhật"):
                    for m in st.session_state.family_data["members"]:
                        if m["name"] == member["name"]:
                            m["interests"] = [interest.strip() for interest in edit_interests.split("\n") if interest.strip()]
                            m["notes"] = edit_notes
                            st.session_state.current_member = m
                            break
                    
                    save_family_data(st.session_state.family_data)
                    st.success("Đã cập nhật thông tin")
                    st.experimental_rerun()
                
                if st.button("Xóa thành viên", type="primary", use_container_width=True):
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
        
        st.button("🗑️ Xóa cuộc hội thoại", on_click=reset_conversation)

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
    
    # --- Hiển thị gợi ý câu hỏi ---
    if st.session_state.current_member:
        suggestions = generate_question_suggestions(st.session_state.current_member)
        cols = st.columns(len(suggestions))
        
        for i, suggestion in enumerate(suggestions):
            if cols[i].button(suggestion, key=f"suggestion_{i}", use_container_width=True):
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