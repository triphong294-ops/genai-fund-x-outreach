from google import genai
from google.genai import types
from pydantic import BaseModel, Field


class OutreachEvaluation(BaseModel):
    is_fit: bool = Field(
        description="True nếu người này là builder, founder, researcher hoặc kỹ sư trong mảng AI models, dev tools, infrastructure, robotics hoặc embodied AI."
    )
    fit_reason: str = Field(
        description="Giải thích ngắn gọn 1-2 câu tại sao họ phù hợp với quỹ đầu tư/hệ sinh thái AI Đông Nam Á của GenAI Fund."
    )
    evidence_quote: str = Field(
        description="Trích dẫn nguyên văn 1 chi tiết có thật từ Bio hoặc Tweet gần đây của họ để làm bằng chứng."
    )
    personalized_dm: str = Field(
        description="Tin nhắn DM dưới 260 ký tự, giọng điệu tự nhiên như một founder/investor đồng nghiệp, nhắc trực tiếp tới evidence_quote, tuyệt đối không bịa đặt sự quen biết."
    )


def analyze_and_draft_dm(
    api_key: str,
    display_name: str,
    username: str,
    bio: str,
    location: str,
    recent_tweets: str,
) -> OutreachEvaluation:
    client = genai.Client(api_key=api_key)

    prompt = f"""
Bạn là chuyên gia tìm kiếm nhân tài và nhà sáng lập (Outreach Associate) tại GenAI Fund — quỹ đầu tư xây dựng hệ sinh thái AI & Robotics tại Đông Nam Á.

Nhiệm vụ: Phân tích hồ sơ X (Twitter) dưới đây và viết 1 tin nhắn DM mở đầu cuộc trò chuyện.

HỒ SƠ ỨNG VIÊN:
- Tên: {display_name} (@{username})
- Địa điểm: {location}
- Bio: {bio}
- Các bài đăng (Tweets) gần đây:
{recent_tweets}

QUY TẮC BẮT BUỘC:
1. Chỉ sử dụng bằng chứng CÓ THẬT trong Bio hoặc Tweets ở trên. Cấm bịa đặt dự án, bài báo hoặc giả vờ đã từng gặp/quen biết.
2. Nếu Bio và Tweets không liên quan đến AI, ML, DevTools, Infra hoặc Robotics/Embodied AI, đặt is_fit = false.
3. Tin nhắn DM (viết bằng tiếng Anh tự nhiên, chuyên nghiệp) phải ngắn gọn (< 260 ký tự), đi thẳng vào chi tiết kỹ thuật/dự án họ vừa chia sẻ, và gợi mở kết nối với GenAI Fund tại Đông Nam Á. Không dùng văn mẫu sáo rỗng ("I hope this finds you well", "synergy").
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=OutreachEvaluation,
            temperature=0.35,
        ),
    )

    return OutreachEvaluation.model_validate_json(response.text)