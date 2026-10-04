import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
import datetime

def scan_thousand_gold_candidates():
    print("🚀 開始執行台股『千金預備軍』掃描機器人...")
    
    # 這裡放我們定義好的 6 大千金 DNA 篩選邏輯
    # (範例資料：實務上連結 FinMind 或 TWSE API 撈取)
    candidates = [
        {"stock_id": "3661", "name": "世芯-KY", "eps_4q": 45.2, "margin": 52.3, "capital": 7.8, "major_holders": 68.5},
        {"stock_id": "5274", "name": "信驊", "eps_4q": 38.6, "margin": 64.1, "capital": 3.8, "major_holders": 72.1},
    ]
    
    df_result = pd.DataFrame(candidates)
    if not df_result.empty:
        df_result = df_result.sort_values(by=["major_holders", "eps_4q"], ascending=False)
    
    return df_result

def send_email_notification(df):
    sender_email = os.environ.get("SENDER_EMAIL")
    sender_password = os.environ.get("SENDER_PASSWORD")
    receiver_email = os.environ.get("RECEIVER_EMAIL")

    if not sender_email or not sender_password or not receiver_email:
        print("⚠️ 未偵測到完整 Email 環境變數，跳過寄信步驟。")
        return

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    subject = f"🎯【千金預備軍】{today_str} 自動過濾與巡檢月報"

    # 製作漂亮的 HTML Email 內容
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #d9534f;">🔥【本月千金預備軍篩選報告】🔥</h2>
        <p>機器人已完成本月財報與籌碼過濾，以下為符合<b>「小股本、高毛利、爆發獲利、大戶鎖碼」</b>之潛在標的：</p>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; text-align: center;">
            <tr style="background-color: #f2f2f2;">
                <th>代號</th>
                <th>股票名稱</th>
                <th>近4季EPS (元)</th>
                <th>毛利率 (%)</th>
                <th>資本額 (億)</th>
                <th>千張大戶持股 (%)</th>
            </tr>
    """

    for _, row in df.iterrows():
        html_content += f"""
            <tr>
                <td><b>{row['stock_id']}</b></td>
                <td>{row['name']}</td>
                <td>{row['eps_4q']}</td>
                <td>{row['margin']}%</td>
                <td>{row['capital']}</td>
                <td><b style="color: #5cb85c;">{row['major_holders']}%</b></td>
            </tr>
        """

    html_content += """
        </table>
        <br>
        <p style="font-size: 12px; color: #777;">💡 本郵件由 Project 1000x Hunter 自動化機器人於每月 10 號發送。</p>
    </body>
    </html>
    """

    # 組裝 Email 郵件
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        # 連接 Gmail SMTP 伺服器寄信
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("📧 Email 通知發送成功！")
    except Exception as e:
        print(f"❌ Email 發送失敗: {e}")

if __name__ == "__main__":
    result_df = scan_thousand_gold_candidates()
    send_email_notification(result_df)
