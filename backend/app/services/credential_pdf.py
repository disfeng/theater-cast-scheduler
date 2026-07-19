from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


def build_actor_credential_pdf(
    *, theater_name: str, actor_name: str, portal_url: str, username: str, password: str
) -> bytes:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=A4)
    document.setTitle(f"{theater_name}-{actor_name}")
    document.setFont("STSong-Light", 20)
    document.drawString(56, 780, f"{theater_name}演员工作台凭证")
    document.setFont("STSong-Light", 12)
    lines = [
        f"演员：{actor_name}",
        f"系统入口：{portal_url}",
        f"用户名：{username}",
        f"初始密码：{password}",
        "首次登录后请立即修改密码。",
        "请勿向任何人泄露演出排班、对位玩家及指定信息。",
    ]
    y = 730
    for line in lines:
        document.drawString(56, y, line)
        y -= 30
    document.save()
    return output.getvalue()
