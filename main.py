import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
import datetime
from FinMind.data import DataLoader

def fetch_and_filter_1000x_candidates():
    print("🚀 開始執行台股『千金預備軍』分級篩選機制 (4/5/6 項條件判斷)...")
    fm = DataLoader()

    try:
        stock_info = fm.taiwan_stock_info()
        valid_stocks = stock_info[
            (~stock_info['stock_id'].str.startswith('00')) & 
            (~stock_info['industry_category'].isin(['金融保險', '建材營造', '觀光餐旅']))
        ]
    except Exception as e:
        print(f"⚠️ 讀取股票基本資料失敗，使用預設測試清單: {e}")
        valid_stocks = pd.DataFrame({'stock_id': ['3661', '5274', '2059', '6669']})

    candidates = []
    today = datetime.date.today()
    start_date = (today - datetime.timedelta(days=365)).strftime("%Y-%m-%d")

    print(f"🔍 開始掃描 {len(valid_stocks)} 檔個股...")

    # 1. 徹底過濾掉權證 (6位數代碼) 與 上市櫃 ETF/存託憑證，只留 4 位數一般個股
    valid_stocks = valid_stocks[valid_stocks['stock_id'].str.len() == 4]

    # 2. 進行全台股完整掃描 (移除 [:30] 限制)
    for stock_id in valid_stocks['stock_id'].tolist():
            
        try:
            # 1. 財報數據 (EPS、毛利率、營益率、資本額)
            financial_data = fm.taiwan_stock_financial_statement(stock_id=stock_id, start_date=start_date)
            if financial_data.empty:
                continue

            latest_4q = financial_data.tail(4)
            if len(latest_4q) < 4:
                continue

            eps_4q = latest_4q[latest_4q['type'] == 'EPS']['value'].sum()
            latest_q = financial_data.tail(1)
            gross_margin = latest_q[latest_q['type'] == 'GrossProfitMargin']['value'].values[0] if 'GrossProfitMargin' in latest_q['type'].values else 0
            operating_margin = latest_q[latest_q['type'] == 'OperatingIncomeMargin']['value'].values[0] if 'OperatingIncomeMargin' in latest_q['type'].values else 0
            capital_billion = latest_q[latest_q['type'] == 'Capital']['value'].values[0] / 100000000 if 'Capital' in latest_q['type'].values else 100

            # 2. 月營收 YoY
            revenue_data = fm.taiwan_stock_month_revenue(stock_id=stock_id, start_date=start_date)
            rev_yoy_3m_avg = revenue_data.tail(3)['revenue_year_growth_ratio'].mean() if not revenue_data.empty else 0

            # 3. 千張大戶持股比
            holder_data = fm.taiwan_stock_holding_shares_per(stock_id=stock_id, start_date=(today - datetime.timedelta(days=30)).strftime("%Y-%m-%d"))
            thousand_share_holders = holder_data[holder_data['HoldingSharesLevel'] == '15']
            major_holder_ratio = thousand_share_holders.tail(1)['percent'].values[0] if not thousand_share_holders.empty else 0

            # ------------------------------------------------------------------
            # 【計算 6 大條件符合數】
            # ------------------------------------------------------------------
            c1 = capital_billion < 30.0         # 資本額 < 30億
            c2 = gross_margin >= 45.0           # 毛利率 > 45%
            c3 = eps_4q >= 20.0                 # 近4季 EPS > 20元
            c4 = rev_yoy_3m_avg >= 20.0         # 營收 YoY > 20%
            c5 = major_holder_ratio >= 60.0     # 大戶持股 > 60%
            c6 = operating_margin >= 20.0       # 營益率 > 20%

            match_count = sum([c1, c2, c3, c4, c5, c6])

            # 只要符合 4 個條件以上就納入分級清單
            if match_count >= 4:
                stock_name = valid_stocks[valid_stocks['stock_id'] == stock_id]['stock_name'].values[0] if 'stock_name' in valid_stocks.columns else stock_id
                
                candidates.append({
                    "stock_id": stock_id,
                    "name": stock_name,
                    "match_count": match_count,
                    "eps_4q": round(eps_4q, 2),
                    "margin": round(gross_margin, 2),
                    "operating_margin": round(operating_margin, 2),
                    "rev_yoy": round(rev_yoy_3m_avg, 2),
                    "capital": round(capital_billion, 2),
                    "major_holders": round(major_holder_ratio, 2)
                })
                print(f"🎯 [{match_count}/6 項符合] {stock_id} {stock_name}")

        except Exception as e:
            continue

    df_result = pd.DataFrame(candidates)
    if not df_result.empty:
        df_result = df_result.sort_values(by=["match_count", "major_holders", "eps_4q"], ascending=[False, False, False])
        
    return df_result

def generate_table_html(df_group, bg_color):
    """輔助函式：產生表格 HTML"""
    if df_group.empty:
        return "<p style='color: #888;'>此區間暫無符合標的。</p>"
    
    html = f"""
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; text-align: center; margin-bottom: 20px;">
        <tr style="background-color: {bg_color}; font-weight: bold;">
            <th>代號</th>
            <th>股票名稱</th>
            <th>近4季EPS (元)</th>
            <th>毛利率 (%)</th>
            <th>營益率 (%)</th>
            <th>營收 YoY (%)</th>
            <th>資本額 (億)</th>
            <th>千張大戶 (%)</th>
        </tr>
    """
    for _, row in df_group.iterrows():
        html += f"""
            <tr>
                <td><b>{row['stock_id']}</b></td>
                <td>{row['name']}</td>
                <td><b>{row['eps_4q']}</b></td>
                <td>{row['margin']}%</td>
                <td>{row['operating_margin']}%</td>
                <td>{row['rev_yoy']}%</td>
                <td>{row['capital']}</td>
                <td><b style="color: #2e7d32;">{row['major_holders']}%</b></td>
            </tr>
        """
    html += "</table>"
    return html

def send_email_notification(df):
    sender_email = os.environ.get("SENDER_EMAIL")
    sender_password = os.environ.get("SENDER_PASSWORD")
    receiver_email = os.environ.get("RECEIVER_EMAIL")

    if not sender_email or not sender_password or not receiver_email:
        print("⚠️ 未偵測到完整 Email 環境變數，跳過寄信步驟。")
        return

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    subject = f"🎯【千金預備軍分級巡檢】{today_str} 自動化月報"

    # 拆分三大梯隊
    df_6 = df[df['match_count'] == 6] if not df.empty else pd.DataFrame()
    df_5 = df[df['match_count'] == 5] if not df.empty else pd.DataFrame()
    df_4 = df[df['match_count'] == 4] if not df.empty else pd.DataFrame()

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <h2 style="color: #d9534f; border-bottom: 2px solid #d9534f; padding-bottom: 8px;">🔥【千金預備軍分級監控報告】🔥</h2>
        <p>機器人已完成全台股財報與籌碼掃描，結果分為 6 項全滿、5 項與 4 項符合梯隊：</p>
        
        <h3 style="color: #d9534f;">🌟 第一梯隊：完全符合 6 大 DNA（頂級預備軍）</h3>
        {generate_table_html(df_6, "#f8d7da")}

        <h3 style="color: #e67e22;">🔥 第二梯隊：符合 5 項條件（強勢黑馬）</h3>
        {generate_table_html(df_5, "#fcf8e3")}

        <h3 style="color: #2980b9;">👀 第三梯隊：符合 4 項條件（潛力觀察名單）</h3>
        {generate_table_html(df_4, "#d9edf7")}

        <br>
        <p style="font-size: 12px; color: #777; border-top: 1px solid #ddd; padding-top: 10px;">
            💡 本郵件由 Project 1000x Hunter 自動化機器人發送。<br>
            評估條件包含：資本額<30億、毛利率>45%、EPS>20元、營收YoY>20%、大戶持股>60%、營益率>20%。
        </p>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("📧 分級 Email 通知發送成功！")
    except Exception as e:
        print(f"❌ Email 發送失敗: {e}")

if __name__ == "__main__":
    result_df = fetch_and_filter_1000x_candidates()
    send_email_notification(result_df)
