import os
import time
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from database import (
    init_db,
    prospect_exists,
    insert_prospect,
    get_prospects_by_status,
    update_dm_and_approve,
    update_status,
    claim_for_sending,
    mark_replied,
)
from ai_service import analyze_and_draft_dm
from x_service import XOutreachClient

load_dotenv()
init_db()

st.set_page_config(
    page_title="GenAI Fund — X Outreach Agent",
    page_icon="🤖",
    layout="wide",
)

# --- SIDEBAR: CẤU HÌNH API & CHẾ ĐỘ AN TOÀN ---
with st.sidebar:
    st.title("⚙️ Cấu hình Hệ thống")
    dry_run = st.toggle(
        "🧪 Dry-Run Mode (Chạy giả lập an toàn)",
        value=True,
        help="Bật để test toàn bộ luồng tìm kiếm, duyệt và gửi DM giả lập mà không tốn phí X API hay gửi tin ra ngoài.",
    )

    st.subheader("🔑 API Credentials (BYOK)")
    gemini_key = st.text_input(
        "Gemini API Key *",
        value=os.getenv("GEMINI_API_KEY", ""),
        type="password",
    )
    x_bearer = st.text_input(
        "X Bearer Token",
        value=os.getenv("X_BEARER_TOKEN", ""),
        type="password",
        disabled=dry_run,
    )
    x_api_key = st.text_input(
        "X API Key (Consumer)",
        value=os.getenv("X_API_KEY", ""),
        type="password",
        disabled=dry_run,
    )
    x_api_secret = st.text_input(
        "X API Secret",
        value=os.getenv("X_API_SECRET", ""),
        type="password",
        disabled=dry_run,
    )
    x_access_token = st.text_input(
        "X Access Token (User)",
        value=os.getenv("X_ACCESS_TOKEN", ""),
        type="password",
        disabled=dry_run,
    )
    x_access_secret = st.text_input(
        "X Access Token Secret",
        value=os.getenv("X_ACCESS_TOKEN_SECRET", ""),
        type="password",
        disabled=dry_run,
    )

    delay_seconds = st.slider(
        "Độ trễ giữa 2 lần gửi DM (giây)",
        min_value=2 if dry_run else 30,
        max_value=180,
        value=3 if dry_run else 60,
        help="Giữ khoảng cách thời gian để tuân thủ chính sách chống spam của X.",
    )

    st.divider()
    st.caption(
        "**Lưu ý giới hạn nền tảng:**\n"
        "- Tài khoản X tắt DM từ người lạ sẽ trả về `403 DM_CLOSED`.\n"
        "- Hệ thống khóa cứng `x_user_id` trong SQLite để chống gửi trùng 100%."
    )

# --- HEADER & METRICS ---
st.title("🚀 GenAI Fund — AI & Robotics Builder Outreach")
if dry_run:
    st.info("🧪 **ĐANG BẬT DRY-RUN MODE:** Dữ liệu mẫu & lệnh gửi giả lập đang hoạt động. Tắt công tắc bên trái để kết nối X API thật.")

drafted_list = get_prospects_by_status(["DRAFTED"])
approved_list = get_prospects_by_status(["APPROVED"])
sent_list = get_prospects_by_status(["SENT", "DM_CLOSED", "FAILED", "RATE_LIMITED"])
replied_list = get_prospects_by_status(["REPLIED"])

c1, c2, c3, c4 = st.columns(4)
c1.metric("📝 Chờ duyệt (Drafted)", len(drafted_list))
c2.metric("✅ Sẵn sàng gửi (Approved)", len(approved_list))
c3.metric("📤 Đã xử lý gửi (Outbound)", len(sent_list))
c4.metric("💬 Đã phản hồi (Replied)", len(replied_list))

tab1, tab2, tab3, tab4 = st.tabs([
    "1️⃣ Tìm kiếm & Phân tích (Discovery)",
    "2️⃣ Duyệt tin nhắn (HITL Review)",
    "3️⃣ Hàng đợi gửi (Safe Sender)",
    "4️⃣ Theo dõi & Phản hồi (Tracker)",
])

x_client = XOutreachClient(
    bearer_token=x_bearer,
    api_key=x_api_key,
    api_secret=x_api_secret,
    access_token=x_access_token,
    access_token_secret=x_access_secret,
    dry_run=dry_run,
)

# ==========================================
# TAB 1: DISCOVERY & AI EVIDENCE EXTRACTION
# ==========================================
with tab1:
    st.subheader("Tìm kiếm Builders, Founders & Researchers")
    mode = st.radio(
        "Nguồn đầu vào:",
        ["Seed X Handles (Khuyên dùng - Ổn định nhất)", "Tìm theo từ khóa (Search Recent Tweets)"],
        horizontal=True,
    )

    if mode.startswith("Seed"):
        handles_input = st.text_area(
            "Nhập danh sách X Handles (cách nhau bằng dấu phẩy hoặc xuống dòng):",
            value="@linh_embodied_ai, @arjun_llm_infra, @siti_ai_agents" if dry_run else "",
            placeholder="@karpathy, @adcock_brett",
        )
        run_discovery = st.button("🔍 Quét Profile & Soạn DM bằng AI", type="primary")
    else:
        keyword_input = st.text_input(
            "Nhập từ khóa lĩnh vực:",
            value="Embodied AI robotics founder" if dry_run else "",
            placeholder="VLA model OR robotics startup OR LLM inference",
        )
        run_discovery = st.button("🔍 Tìm theo từ khóa & Soạn DM", type="primary")

    if run_discovery:
        if not gemini_key:
            st.error("Vui lòng nhập **Gemini API Key** ở thanh bên trái trước khi chạy.")
        else:
            with st.spinner("Đang thu thập dữ liệu từ X và phân tích bằng chứng bằng Gemini..."):
                if mode.startswith("Seed"):
                    raw_items = [h.strip() for h in handles_input.replace("\n", ",").split(",") if h.strip()]
                    profiles, errs = x_client.fetch_by_handles(raw_items)
                else:
                    profiles, errs = x_client.search_by_keyword(keyword_input)

                for err in errs:
                    st.warning(err)

                added_count = 0
                skipped_count = 0
                for p in profiles:
                    if prospect_exists(p["x_user_id"]):
                        skipped_count += 1
                        continue

                    try:
                        eval_res = analyze_and_draft_dm(
                            api_key=gemini_key,
                            display_name=p["display_name"],
                            username=p["username"],
                            bio=p["bio"],
                            location=p["location"],
                            recent_tweets=p["recent_tweets"],
                        )
                        p["is_fit"] = eval_res.is_fit
                        p["fit_reason"] = eval_res.fit_reason
                        p["evidence_quote"] = eval_res.evidence_quote
                        p["dm_text"] = eval_res.personalized_dm
                        p["status"] = "DRAFTED" if eval_res.is_fit else "REJECTED"

                        if insert_prospect(p):
                            added_count += 1
                    except Exception as e:
                        st.error(f"Lỗi Gemini khi phân tích @{p['username']}: {e}")

                st.success(f"Hoàn tất! Đã thêm **{added_count}** hồ sơ mới (Bỏ qua **{skipped_count}** hồ sơ đã tồn tại trong DB).")
                time.sleep(1)
                st.rerun()

# ==========================================
# TAB 2: HUMAN-IN-THE-LOOP APPROVAL
# ==========================================
with tab2:
    st.subheader("Kiểm duyệt bằng chứng & Chỉnh sửa nội dung DM")
    if not drafted_list:
        st.info("Hiện không có bản nháp nào chờ duyệt. Hãy sang Tab 1 để quét thêm ứng viên.")
    else:
        for item in drafted_list:
            with st.container(border=True):
                col_info, col_dm = st.columns([1.1, 1.2])
                with col_info:
                    st.markdown(f"### {item['display_name']} (`@{item['username']}`)")
                    if item["location"]:
                        st.caption(f"📍 {item['location']}")
                    st.markdown(f"**Bio:** {item['bio']}")
                    st.success(f"**🎯 Lý do phù hợp (Why Fit):** {item['fit_reason']}")
                    st.info(f"**📌 Bằng chứng trích dẫn:** {item['evidence_quote']}")
                    with st.expander("Xem Tweets gốc đã thu thập"):
                        st.text(item["recent_tweets"])

                with col_dm:
                    edited_dm = st.text_area(
                        "Nội dung DM sẽ gửi (Có thể sửa trực tiếp):",
                        value=item["dm_text"],
                        height=140,
                        key=f"dm_edit_{item['x_user_id']}",
                    )
                    st.caption(f"Độ dài: {len(edited_dm)} / 280 ký tự")

                    b1, b2 = st.columns(2)
                    if b1.button("✅ Approve & Đưa vào hàng đợi", key=f"app_{item['x_user_id']}", type="primary"):
                        update_dm_and_approve(item["x_user_id"], edited_dm)
                        st.rerun()
                    if b2.button("🗑️ Reject (Bỏ qua)", key=f"rej_{item['x_user_id']}"):
                        update_status(item["x_user_id"], "REJECTED", "Rejected by human reviewer")
                        st.rerun()

# ==========================================
# TAB 3: RATE-LIMITED SAFE OUTBOUND SENDER
# ==========================================
with tab3:
    st.subheader("Hàng đợi gửi DM (Chống trùng lặp & Giới hạn tốc độ)")
    if not approved_list:
        st.info("Chưa có tin nhắn nào được duyệt (`APPROVED`).")
    else:
        st.write(f"Có **{len(approved_list)}** tin nhắn đã được duyệt và sẵn sàng gửi.")
        for item in approved_list:
            st.markdown(f"- **@{item['username']}**: _{item['dm_text']}_")

        if st.button("🚀 Bắt đầu gửi các tin đã Approve", type="primary"):
            progress = st.progress(0)
            status_box = st.empty()

            for idx, item in enumerate(approved_list):
                uid = item["x_user_id"]
                # Bước khóa nguyên tử chống gửi đúp
                if not claim_for_sending(uid):
                    status_box.warning(f"Bỏ qua @{item['username']} vì đã được xử lý trước đó.")
                    continue

                status_box.info(f"Đang gửi DM tới @{item['username']} ({idx + 1}/{len(approved_list)})...")
                send_status, err_msg = x_client.send_direct_message(uid, item["dm_text"])
                update_status(uid, send_status, err_msg)

                progress.progress((idx + 1) / len(approved_list))
                if idx < len(approved_list) - 1:
                    time.sleep(delay_seconds)

            status_box.success("Đã hoàn tất phiên gửi tin!")
            time.sleep(1)
            st.rerun()

# ==========================================
# TAB 4: SENT LOGS & REPLY TRACKING
# ==========================================
with tab4:
    st.subheader("Nhật ký chiến dịch & Theo dõi phản hồi")
    col_sync, col_export = st.columns([1, 4])
    if col_sync.button("🔄 Kiểm tra phản hồi mới (Sync Replies)"):
        sent_ids = [r["x_user_id"] for r in get_prospects_by_status(["SENT"])]
        replies = x_client.fetch_incoming_replies(sent_ids)
        for uid, text in replies.items():
            mark_replied(uid, text)
        st.success(f"Đã đồng bộ! Phát hiện **{len(replies)}** phản hồi mới.")
        time.sleep(1)
        st.rerun()

    all_records = get_prospects_by_status(["REPLIED", "SENT", "DM_CLOSED", "FAILED", "RATE_LIMITED", "REJECTED"])
    if all_records:
        df = pd.DataFrame(all_records)[
            ["username", "display_name", "status", "dm_text", "reply_text", "sent_at", "error_log"]
        ]
        st.dataframe(df, use_container_width=True)

        csv_data = df.to_csv(index=False).encode("utf-8")
        col_export.download_button(
            "📥 Xuất báo cáo CSV",
            data=csv_data,
            file_name="genaifund_outreach_log.csv",
            mime="text/csv",
        )
    else:
        st.info("Chưa có lịch sử gửi tin nào.")