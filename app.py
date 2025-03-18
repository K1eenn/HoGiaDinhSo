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

# Tải các biến môi trường từ file .env
dotenv.load_dotenv()

# Chỉ sử dụng mô hình GPT-4o-mini
openai_model = "gpt-4o-mini"

# Hàm để lưu và tải dữ liệu gia đình
def save_family_data(data):
    with open("family_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_family_data():
    try:
        with open("family_data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Trả về cấu trúc dữ liệu mẫu nếu file không tồn tại hoặc trống
        return {
            "members": {},
            "events": [],
            "notes": []
        }

# Hàm để truy xuất thông tin thành viên gia đình cho AI
def get_family_context():
    data = load_family_data()
    context = "Thông tin về các thành viên trong gia đình:\n\n"
    
    for member_id, member in data["members"].items():
        context += f"- {member['name']} ({member['relationship']}, {member['age']} tuổi)\n"
        context += f"  + Sở thích: {', '.join(member['preferences'])}\n"
        context += f"  + Dị ứng/Hạn chế: {', '.join(member['restrictions'])}\n"
        context += f"  + Ghi chú: {member['notes']}\n\n"
    
    # Thêm các sự kiện sắp tới
    context += "Các sự kiện sắp tới:\n"
    today = datetime.datetime.now().date()
    upcoming_events = [e for e in data["events"] 
                      if datetime.datetime.strptime(e["date"], "%Y-%m-%d").date() >= today]
    
    for event in sorted(upcoming_events, key=lambda x: x["date"]):
        event_date = datetime.datetime.strptime(event["date"], "%Y-%m-%d").date()
        days_remaining = (event_date - today).days
        context += f"- {event['title']} ({event['date']}): {event['description']} - {days_remaining} ngày nữa\n"
    
    return context

# Function để chuyển file ảnh sang base64
def get_image_base64(image_raw):
    buffered = BytesIO()
    image_raw.save(buffered, format=image_raw.format)
    img_byte = buffered.getvalue()
    return base64.b64encode(img_byte).decode('utf-8')

# Function để query và stream phản hồi từ GPT-4o-mini
def stream_llm_response(api_key=None):
    response_message = ""
    
    # Tạo ngữ cảnh gia đình cho AI
    family_context = get_family_context()
    
    # Thêm ngữ cảnh vào tin nhắn hệ thống
    system_message = {
        "role": "system", 
        "content": f"""Bạn là trợ lý gia đình thông minh. Nhiệm vụ của bạn là hỗ trợ và tư vấn cho các thành viên 
        trong gia đình về mọi vấn đề liên quan đến cuộc sống hàng ngày, kế hoạch, sở thích và nhu cầu của họ.
        
        {family_context}
        
        Hãy sử dụng thông tin này để cá nhân hóa câu trả lời của bạn. Khi người dùng hỏi về một thành viên cụ thể, 
        hãy đưa ra gợi ý phù hợp với sở thích và hạn chế của họ. Nếu họ hỏi về kế hoạch, hãy nhắc họ về các sự kiện sắp tới."""
    }
    
    # Thêm tin nhắn hệ thống vào đầu danh sách
    messages = [system_message] + st.session_state.messages
    
    client = OpenAI(api_key=api_key)
    for chunk in client.chat.completions.create(
        model=openai_model,
        messages=messages,
        temperature=0.7,
        max_tokens=4096,
        stream=True,
    ):
        chunk_text = chunk.choices[0].delta.content or ""
        response_message += chunk_text
        yield chunk_text

    st.session_state.messages.append({
        "role": "assistant", 
        "content": [
            {
                "type": "text",
                "text": response_message,
            }
        ]})

def main():
    # --- Cấu hình trang ---
    st.set_page_config(
        page_title="Trợ lý Gia đình AI",
        page_icon="👨‍👩‍👧‍👦",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # --- Header ---
    st.html("""<h1 style="text-align: center; color: #6ca395;">👨‍👩‍👧‍👦 <i>Trợ lý Gia đình AI</i> 🏡</h1>""")
    
    # --- Thanh bên ---
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        default_openai_api_key = os.getenv("OPENAI_API_KEY") or ""
        openai_api_key = st.text_input("OpenAI API Key:", value=default_openai_api_key, type="password")
        
        st.divider()
        
        # Tab để quản lý thành viên gia đình
        st.header("👨‍👩‍👧‍👦 Quản lý Gia đình")
        tab1, tab2, tab3 = st.tabs(["Thành viên", "Sự kiện", "Ghi chú"])
        
        with tab1:
            family_data = load_family_data()
            
            # Hiển thị danh sách thành viên
            if family_data["members"]:
                st.subheader("Thành viên hiện tại:")
                for member_id, member in family_data["members"].items():
                    st.write(f"{member['name']} ({member['relationship']}, {member['age']} tuổi)")
                    
                    # Nút để xem/chỉnh sửa thành viên
                    if st.button(f"Chỉnh sửa {member['name']}", key=f"edit_{member_id}"):
                        st.session_state.edit_member = member_id
            
            # Form để thêm thành viên mới
            with st.expander("➕ Thêm thành viên mới"):
                with st.form("add_member_form"):
                    new_name = st.text_input("Tên:")
                    new_relationship = st.text_input("Quan hệ (ví dụ: Cha, Mẹ, Con):")
                    new_age = st.number_input("Tuổi:", min_value=0, max_value=120)
                    new_preferences = st.text_area("Sở thích (mỗi sở thích một dòng):")
                    new_restrictions = st.text_area("Dị ứng/Hạn chế (mỗi hạn chế một dòng):")
                    new_notes = st.text_area("Ghi chú:")
                    
                    submit_button = st.form_submit_button("Thêm")
                    
                    if submit_button and new_name:
                        # Tạo ID mới cho thành viên
                        new_id = str(len(family_data["members"]) + 1)
                        
                        # Thêm thành viên mới
                        family_data["members"][new_id] = {
                            "name": new_name,
                            "relationship": new_relationship,
                            "age": new_age,
                            "preferences": [p.strip() for p in new_preferences.split("\n") if p.strip()],
                            "restrictions": [r.strip() for r in new_restrictions.split("\n") if r.strip()],
                            "notes": new_notes
                        }
                        
                        # Lưu dữ liệu
                        save_family_data(family_data)
                        st.success(f"Đã thêm {new_name} vào gia đình!")
                        st.rerun()
            
            # Form để chỉnh sửa thành viên
            if "edit_member" in st.session_state and st.session_state.edit_member:
                member_id = st.session_state.edit_member
                member = family_data["members"][member_id]
                
                st.subheader(f"Chỉnh sửa thông tin của {member['name']}")
                
                with st.form("edit_member_form"):
                    edit_name = st.text_input("Tên:", value=member["name"])
                    edit_relationship = st.text_input("Quan hệ:", value=member["relationship"])
                    edit_age = st.number_input("Tuổi:", min_value=0, max_value=120, value=member["age"])
                    edit_preferences = st.text_area("Sở thích:", value="\n".join(member["preferences"]))
                    edit_restrictions = st.text_area("Dị ứng/Hạn chế:", value="\n".join(member["restrictions"]))
                    edit_notes = st.text_area("Ghi chú:", value=member["notes"])
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        update_button = st.form_submit_button("Cập nhật")
                    with col2:
                        delete_button = st.form_submit_button("Xóa", type="primary")
                    
                    if update_button:
                        # Cập nhật thông tin
                        family_data["members"][member_id] = {
                            "name": edit_name,
                            "relationship": edit_relationship,
                            "age": edit_age,
                            "preferences": [p.strip() for p in edit_preferences.split("\n") if p.strip()],
                            "restrictions": [r.strip() for r in edit_restrictions.split("\n") if r.strip()],
                            "notes": edit_notes
                        }
                        
                        # Lưu dữ liệu
                        save_family_data(family_data)
                        st.success(f"Đã cập nhật thông tin của {edit_name}!")
                        st.session_state.edit_member = None
                        st.rerun()
                    
                    if delete_button:
                        # Xóa thành viên
                        name = family_data["members"][member_id]["name"]
                        del family_data["members"][member_id]
                        
                        # Lưu dữ liệu
                        save_family_data(family_data)
                        st.success(f"Đã xóa {name} khỏi gia đình!")
                        st.session_state.edit_member = None
                        st.rerun()
        
        with tab2:
            # Quản lý các sự kiện gia đình
            with st.expander("➕ Thêm sự kiện mới"):
                with st.form("add_event_form"):
                    event_title = st.text_input("Tiêu đề sự kiện:")
                    event_date = st.date_input("Ngày:")
                    event_description = st.text_area("Mô tả:")
                    
                    submit_event = st.form_submit_button("Thêm sự kiện")
                    
                    if submit_event and event_title:
                        # Thêm sự kiện mới
                        family_data["events"].append({
                            "title": event_title,
                            "date": event_date.strftime("%Y-%m-%d"),
                            "description": event_description
                        })
                        
                        # Lưu dữ liệu
                        save_family_data(family_data)
                        st.success(f"Đã thêm sự kiện {event_title}!")
                        st.rerun()
            
            # Hiển thị các sự kiện sắp tới
            if family_data["events"]:
                st.subheader("Sự kiện sắp tới:")
                today = datetime.datetime.now().date()
                events = sorted(family_data["events"], key=lambda x: x["date"])
                
                for i, event in enumerate(events):
                    event_date = datetime.datetime.strptime(event["date"], "%Y-%m-%d").date()
                    days_remaining = (event_date - today).days
                    
                    # Hiển thị ngày còn lại
                    status = ""
                    if days_remaining < 0:
                        status = "Đã qua"
                    elif days_remaining == 0:
                        status = "Hôm nay"
                    else:
                        status = f"Còn {days_remaining} ngày"
                    
                    st.write(f"**{event['title']}** ({event['date']}) - {status}")
                    st.write(f"{event['description']}")
                    
                    # Nút xóa sự kiện
                    if st.button(f"Xóa", key=f"delete_event_{i}"):
                        family_data["events"].pop(i)
                        save_family_data(family_data)
                        st.success("Đã xóa sự kiện!")
                        st.rerun()
                    
                    st.divider()
        
        with tab3:
            # Quản lý ghi chú gia đình
            with st.form("add_note_form"):
                note_content = st.text_area("Ghi chú mới:")
                submit_note = st.form_submit_button("Thêm ghi chú")
                
                if submit_note and note_content:
                    # Thêm ghi chú mới với thời gian hiện tại
                    family_data["notes"].append({
                        "content": note_content,
                        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                    # Lưu dữ liệu
                    save_family_data(family_data)
                    st.success("Đã thêm ghi chú mới!")
                    st.rerun()
            
            # Hiển thị ghi chú hiện có
            if family_data["notes"]:
                st.subheader("Ghi chú:")
                for i, note in enumerate(reversed(family_data["notes"])):
                    st.markdown(f"**{note['timestamp']}**")
                    st.markdown(note["content"])
                    
                    # Nút xóa ghi chú
                    if st.button(f"Xóa", key=f"delete_note_{i}"):
                        family_data["notes"].pop(len(family_data["notes"]) - 1 - i)
                        save_family_data(family_data)
                        st.success("Đã xóa ghi chú!")
                        st.rerun()
                    
                    st.divider()
        
        # Nút reset cuộc trò chuyện
        st.divider()
        def reset_conversation():
            if "messages" in st.session_state and len(st.session_state.messages) > 0:
                st.session_state.pop("messages", None)

        st.button(
            "🗑️ Làm mới cuộc trò chuyện", 
            on_click=reset_conversation,
        )

    # --- Kiểm tra API Key ---
    if openai_api_key == "" or openai_api_key is None or "sk-" not in openai_api_key:
        st.write("#")
        st.warning("⬅️ Vui lòng nhập OpenAI API Key để tiếp tục...")
    else:
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Hiển thị tin nhắn trước đó nếu có
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                for content in message["content"]:
                    if content["type"] == "text":
                        st.write(content["text"])
                    elif content["type"] == "image_url":      
                        st.image(content["image_url"]["url"])

        # Khu vực tương tác chính
        col1, col2 = st.columns([3, 1])
        
        with col2:
            st.write("### 📸 Thêm hình ảnh:")
            
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
            
            cols_img = st.columns(2)
            with cols_img[0]:
                st.file_uploader(
                    "Tải ảnh lên:", 
                    type=["png", "jpg", "jpeg"],
                    accept_multiple_files=False,
                    key="uploaded_img",
                    on_change=add_image_to_messages,
                )
            
            with cols_img[1]:
                st.camera_input(
                    "Chụp ảnh", 
                    key="camera_img",
                    on_change=add_image_to_messages,
                )
            
            st.write("### 🎤 Thu âm giọng nói:")
            speech_input = audio_recorder("Bấm để nói:", icon_size="2x", neutral_color="#6ca395")
            
            if speech_input and "prev_speech_hash" in st.session_state and st.session_state.prev_speech_hash != hash(speech_input):
                st.session_state.prev_speech_hash = hash(speech_input)
                
                client = OpenAI(api_key=openai_api_key)
                transcript = client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=("audio.wav", speech_input),
                )
                
                audio_prompt = transcript.text
                
                if audio_prompt:
                    st.session_state.messages.append(
                        {
                            "role": "user", 
                            "content": [{
                                "type": "text",
                                "text": audio_prompt,
                            }]
                        }
                    )
                    
                    # Hiển thị tin nhắn mới
                    with st.chat_message("user"):
                        st.markdown(audio_prompt)
                    
                    # Phản hồi từ AI
                    with st.chat_message("assistant"):
                        st.write_stream(stream_llm_response(api_key=openai_api_key))
        
        with col1:
            # Nhập tin nhắn
            if prompt := st.chat_input("Hỏi trợ lý gia đình..."):
                st.session_state.messages.append(
                    {
                        "role": "user", 
                        "content": [{
                            "type": "text",
                            "text": prompt,
                        }]
                    }
                )
                
                # Hiển thị tin nhắn mới
                with st.chat_message("user"):
                    st.markdown(prompt)
                
                # Phản hồi từ AI
                with st.chat_message("assistant"):
                    st.write_stream(stream_llm_response(api_key=openai_api_key))


if __name__=="__main__":
    if "prev_speech_hash" not in st.session_state:
        st.session_state.prev_speech_hash = None
    if "edit_member" not in st.session_state:
        st.session_state.edit_member = None
    main()