import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
import datetime
from FinMind.data import DataLoader

def fetch_and_filter_1000x_candidates():
    print("🚀 開始執行台股『千金預備軍』6 大 DNA 自動篩選機制...")
    fm = DataLoader()
    
    # --------------------------------------------------------------------------
    # 【千金預備軍 6 大硬核篩選標準】
    # 1. 股本過濾 (Capital < 30 億 TWD)：籌碼極度稀缺，主力拉抬成本低。
    # 2. 高毛利率 (Gross Margin > 45%)：產品具高定價權與技術護城河。
    # 3. 超高獲利 (近 4 季 EPS > 20 元)：具備邁向千金（需要 EPS 30-50元）的基因。
    # 4. 高營收成長 (近 3 個月單月營收 YoY > 20%)：處於爆發成長期。
    # 5. 主力大戶鎖碼 (千張大戶持股比 > 60%)：浮碼已被大戶保險箱徹底鎖死。
    # 6. 高營業利益率 (Operating Margin > 20%)：輕資產/IP/高附加價值模式。
    # --------------------------------------------------------------------------

    # 1. 取得台股所有上櫃與上市股票清單
    # 實務上 FinMind 提供 TaiwanStockInfo API
    try:
        stock_info = fm.taiwan_stock_info()
        # 排除 ETF、存託憑證與金融業，專注於半導體、高階硬體與 IP/SaaS
        valid_stocks = stock_info[
            (~stock_info['stock_id'].str.startswith('00')) & 
            (~stock_info['industry_category'].isin(['金融保險', '建材營造', '觀光餐旅']))
        ]
    except Exception as e:
        print(f"⚠️ 讀取股票基本資料失敗，使用預設監控陣列測試: {e}")
        # 備用清單：包含世芯、信驊、川湖、緯穎等高獲利標的做掃描測試
        valid_stocks = pd.DataFrame({'stock_id': ['3661', '5274', '2059', '6669']})

    candidates = []

    # 設定查詢時間範圍
    today = datetime.date.today()
    start_date = (today - datetime.timedelta(days=365)).strftime("%Y-%m-%d")

    print(f"🔍 開始掃描 {len(valid_stocks)} 檔個股基本面與籌碼面數據...")

    for stock_id in valid_stocks['stock_id'].tolist()[:30]: # 範例先測試前 30 檔
        try:
            # ------------------------------------------------------------------
            # 【DNA 1 & 2 & 6】財務報表：資本額、毛利率、營業利益率、EPS
            # API: TaiwanStockFinancialStatements
            # ------------------------------------------------------------------
            financial_data = fm.taiwan_stock_financial_statement(
                stock_id=stock_id,
                start_date=start_date
            )
            
            if financial_data.empty:
                continue

            # 抓取最近 4 季數據計算
            latest_4q = financial_data.tail(4)
            if len(latest_4q) < 4:
                continue

            # 計算近四季總 EPS
            eps_4q = latest_4q[latest_4q['type'] == 'EPS']['value'].sum()
            
            # 計算最新一季毛利率 (Gross Margin) 與 營業利益率 (Operating Margin)
            latest_q = financial_data.tail(1)
            gross_margin = latest_q[latest_q['type'] == 'GrossProfitMargin']['value'].values[0] if 'GrossProfitMargin' in latest_q['type'].values else 0
            operating_margin = latest_q[latest_q['type'] == 'OperatingIncomeMargin']['value'].values[0] if 'OperatingIncomeMargin' in latest_q['type'].values else 0
            
            # 讀取實收資本額 (億)
            capital_billion = latest_q[latest_q['type'] == 'Capital']['value'].values[0] / 100000000 if 'Capital' in latest_q['type'].values else 100

            # ------------------------------------------------------------------
            # 【DNA 3】營收爆發力：近 3 個月平均營收年增率 (YoY)
            # API: TaiwanStockMonthRevenue
            # ------------------------------------------------------------------
            revenue_data = fm.taiwan_stock_month_revenue(
                stock_id=stock_id,
                start_date=start_date
            )
            rev_yoy_3m_avg = revenue_data.tail(3)['revenue_year_growth_ratio'].mean() if not revenue_data.empty else 0

            # ------------------------------------------------------------------
            # 【DNA 5】大戶籌碼：千張大戶持股比例
            # API: TaiwanStockHoldingSharesPer
            # ------------------------------------------------------------------
            holder_data = fm.taiwan_stock_holding_shares_per(
                stock_id=stock_id,
                start_date=(today - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
            )
            # 15 代表 1000 張以上的級別
            thousand_share_holders = holder_data[holder_data['HoldingSharesLevel'] == '15']
            major_holder_ratio = thousand_share_holders.tail(1)['percent'].values[0] if not thousand_share_holders.empty else 0

            # ------------------------------------------------------------------
            # 【執行 6 大 DNA 硬核條件過濾】
            # ------------------------------------------------------------------
            cond_1 = capital_billion < 30.0         # 1. 股本 < 30 億 TWD
            cond_2 = gross_margin >= 45.0           # 2. 毛利率 > 45%
            cond_3 = eps_4q >= 20.0                 # 3. 近 4 季 EPS > 20 元
            cond_4 = rev_yoy_3m_avg >= 20.0         # 4. 近 3 個月營收 YoY > 20%
            cond_5 = major_holder_ratio >= 60.0     # 5. 千張大戶持股比 > 60%
            cond_6 = operating_margin >= 20.0       # 6. 營業利益率 > 20%

            if cond_1 and cond_2 and cond_3 and cond_4 and cond_5 and cond_6:
                # 撈取股票名稱
                stock_name = valid_stocks[valid_stocks['stock_id'] == stock_id]['stock_name'].values[0] if 'stock_name' in valid_stocks.columns else stock_id
                
                candidates.append({
                    "stock_id": stock_id,
                    "name": stock_name,
                    "eps_4q": round(eps_4q, 2),
                    "margin": round(gross_margin, 2),
                    "operating_margin": round(operating_margin, 2),
                    "rev_yoy": round(rev_yoy_3m_avg, 2),
                    "capital": round(capital_billion, 2),
                    "major_holders": round(major_holder_ratio, 2)
                })
                print(f"✅ 發現符合千金 DNA 標的：{stock_id} (EPS: {eps_4q:.2f}, 大戶持股: {major_holder_ratio:.2f}%)")

        except Exception as e:
            continue

    df_result = pd.DataFrame(candidates)
    
    if not df_result.empty:
        # 依照『千張大戶持股比』與『近四季EPS』進行綜合排序
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

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #d9534f;">🔥【本月千金預備軍篩選報告】🔥</h2>
        <p>機器人已完成本月財報與籌碼過濾，以下為完全通過<b>「6 大千金 DNA」</b>驗證之潛在標的：</p>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; text-align: center;">
            <tr style="background-color: #f2f2f2;">
                <th>代號</th>
                <th>股票名稱</th>
                <th>近4季EPS (元)</th>
                <th>毛利率 (%)</th>
                <th>營益率 (%)</th>
                <th>營收 YoY (%)</th>
                <th>資本額 (億)</th>
                <th>千張大戶持股 (%)</th>
            </tr>
    """

    if df.empty:
        html_content += """
            <tr>
                <td colspan="8" style="color: #888;">本月無符合 6 大嚴格千金條件之個股。</td>
            </tr>
        """
    else:
        for _, row in df.iterrows():
            html_content += f"""
                <tr>
                    <td><b>{row['stock_id']}</b></td>
                    <td>{row['name']}</td>
                    <td><b>{row['eps_4q']}</b></td>
                    <td>{row['margin']}%</td>
                    <td>{row['operating_margin']}%</td>
                    <td>{row['rev_yoy']}%</td>
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

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("📧 Email 通知發送成功！")
    except Exception as e:
        print(f"❌ Email 發送失敗: {e}")

if __name__ == "__main__":
    result_df = fetch_and_filter_1000x_candidates()
    send_email_notification(result_df)
