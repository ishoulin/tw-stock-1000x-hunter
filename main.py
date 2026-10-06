import os
import time
import smtplib
import datetime
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from FinMind.data import DataLoader

def fetch_and_filter_1000x_candidates():
    # ... 前面抓取股票清單等邏輯 ...

    # 針對特定指標股開啟 DEBUG 診斷印出
    debug_stocks = ['2330', '2454', '3661']  # 👈 在迴圈外補上這行
    
    print("🚀 開始執行台股『千金預備軍』分級篩選機制 (4/5/6 項條件判斷)...")
    fm = DataLoader()
   
    today = datetime.date.today()
    start_date = (today - datetime.timedelta(days=365)).strftime("%Y-%m-%d") 
    
    try:
        stock_info = fm.taiwan_stock_info()
        
        # 1. 修正 FinMind 正確欄位名稱 (market) 與產業過濾
        valid_stocks = stock_info[
            (stock_info['stock_id'].str.isdigit()) & 
            (stock_info['stock_id'].str.len() == 4) &
            (stock_info['type'].isin(['twse', 'tpex'])) &  # 👈 修正為 FinMind 的真實 Market 名稱
            (~stock_info['industry_category'].isin([
                '金融保險', '建材營造', '觀光餐旅', '金融保險業', '建材營造業', '觀光事業'
            ])) &
            (~stock_info['stock_name'].str.contains('ETF|TDR|特別股|創|正2|反1', na=False))
        ].copy()

        raw_list = valid_stocks['stock_id'].tolist()
        print(f"🧹 基本產業過濾完成，剩餘普通股: {len(raw_list)} 檔")

        # ------------------------------------------------------------------
        # 2. 免費版相容快篩 (加上獨立 try，避免免費版權限限制中斷流程)
        # ------------------------------------------------------------------
        stock_list = raw_list
        try:
            # 使用免費版允許的全市場單日個股 API
            recent_date = (today - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
            price_data = fm.taiwan_stock_price_all(date=recent_date)

            if price_data is not None and not price_data.empty:
                # 濾網：收盤價 >= 25 元 且 成交量 >= 50,000 股 (50張)
                qualified = price_data[
                    (price_data['close'] >= 25) & 
                    (price_data['Trading_Volume'] >= 50000)
                ]
                valid_set = set(qualified['stock_id'].unique())
                valid_set.update(debug_stocks)  # 強制保留 Debug 測試股

                stock_list = [s for s in raw_list if s in valid_set]
                valid_stocks = valid_stocks[valid_stocks['stock_id'].isin(stock_list)]
                print(f"🎯 股價流動性快篩完成！目標成功精簡為 {len(stock_list)} 檔！\n")
            else:
                print("ℹ️ 未取得單日股價快篩資料，自動降級為全量普通股掃描...")
        except Exception as filter_err:
            print(f"ℹ️ 快篩遇到 API 限制或假日無資料 ({filter_err})，自動降級為全量普通股掃描...")

        total_count = len(stock_list)
                              
    except Exception as e:
        print(f"⚠️ 讀取股票基本資料失敗: {e}")
        return pd.DataFrame()

    candidates = []
    today = datetime.date.today()
    start_date = (today - datetime.timedelta(days=365)).strftime("%Y-%m-%d")

    stock_list = valid_stocks['stock_id'].tolist()
    total_count = len(stock_list)
    print(f"🔍 已精準過濾非上市櫃標的，正式開始掃描台股 {total_count} 檔普通股...")

        
    for idx, stock_id in enumerate(stock_list, 1):
        # 判斷當前這檔是否為診斷股票
        is_debug = stock_id in debug_stocks
    
        if is_debug:
            print(f"\n⚡ [DEBUG] 開始處理指標股: {stock_id}")
        try:
            # 1. 財報數據 (EPS、毛利率、營益率、資本額)
            financial_data = fm.taiwan_stock_financial_statement(stock_id=stock_id, start_date=start_date)
            if financial_data is None or financial_data.empty:
                continue

            # 抓取 EPS (支援 EPS / EPS(元) 等相容名稱)
            eps_df = financial_data[financial_data['type'].str.contains('EPS', case=False, na=False)]
            latest_4q_eps = eps_df.tail(4)
            if len(latest_4q_eps) < 4:
                continue
            eps_4q = latest_4q_eps['value'].sum()
            latest_4q = financial_data[financial_data['type'] == 'EPS'].tail(4)
            if len(latest_4q) < 4:
                continue
            eps_4q = latest_4q['value'].sum()

            # 抓取最近一季的毛利率、營益率與資本額
            gross_df = financial_data[financial_data['type'] == 'GrossProfitMargin']
            gross_margin = gross_df.tail(1)['value'].values[0] if not gross_df.empty else 0

            # 抓取營益率 (OperatingIncomeMargin / OperatingMargin)
            oper_df = financial_data[financial_data['type'] == 'OperatingIncomeMargin']
            operating_margin = oper_df.tail(1)['value'].values[0] if not oper_df.empty else 0

            cap_df = financial_data[financial_data['type'] == 'Capital']
            capital_billion = cap_df.tail(1)['value'].values[0] / 100000000 if not cap_df.empty else 100

            # 2. 月營收 YoY
            revenue_data = fm.taiwan_stock_month_revenue(stock_id=stock_id, start_date=start_date)
            if revenue_data is None or revenue_data.empty:
                rev_yoy_3m_avg = 0.0
            else:
                # 相容欄位名稱處理
                yoy_col = 'revenue_year_growth_ratio' if 'revenue_year_growth_ratio' in revenue_data.columns else 'year_growth_ratio'
                rev_yoy_3m_avg = revenue_data.tail(3)[yoy_col].mean() if yoy_col in revenue_data.columns else 0.0
            
            # 3. 千張大戶持股比
            holder_data = fm.taiwan_stock_holding_shares_per(
                stock_id=stock_id, 
                start_date=(today - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
            )
            if holder_data is None or holder_data.empty:
                major_holder_ratio = 0
            else:
                thousand_share_holders = holder_data[holder_data['HoldingSharesLevel'] == '15']
                major_holder_ratio = thousand_share_holders.tail(1)['percent'].values[0] if not thousand_share_holders.empty else 0

            
            # ------------------------------------------------------------------
            # 【判斷 6 大條件符合數 - 2026 10月版】
            # ------------------------------------------------------------------
            c1 = capital_billion < 60.0         # 資本額 < 60億
            c2 = gross_margin >= 30.0           # 毛利率 > 30%
            c3 = eps_4q >= 12.0                 # 近4季 EPS > 12元
            c4 = rev_yoy_3m_avg >= 10.0         # 營收 YoY > 10%
            c5 = major_holder_ratio >= 50.0     # 大戶持股 > 50%
            c6 = operating_margin >= 15.0       # 營益率 > 15%

            match_count = sum([c1, c2, c3, c4, c5, c6])
 
            # ------------------------------------------------------------------
            # 3. 計算完畢後，如果是指標股就強制印出數值
            # ------------------------------------------------------------------
            if is_debug:
                print(f"================ [DEBUG 診斷: {stock_id}] ================")
                print(f"1. 資本額 (億): {capital_billion:.2f} (c1 < 60: {c1})")
                print(f"2. 毛利率 (%): {gross_margin:.2f}% (c2 >= 30%: {c2})")
                print(f"3. 近 4 季 EPS: {eps_4q:.2f} (c3 >= 12: {c3})")
                print(f"4. 營收 YoY (%): {rev_yoy_3m_avg:.2f}% (c4 >= 10%: {c4})")
                print(f"5. 大戶持股 (%): {major_holder_ratio:.2f}% (c5 >= 50%: {c5})")
                print(f"6. 營益率 (%): {operating_margin:.2f}% (c6 >= 15%: {c6})")
                print(f"👉 符合項目數: {match_count} / 6")
                print(f"========================================================\n")
   
            # 符合 4 個或以上就放入結果
            if match_count >= 4:
                stock_name_series = valid_stocks[valid_stocks['stock_id'] == stock_id]['stock_name']
                stock_name = stock_name_series.values[0] if not stock_name_series.empty else stock_id
                
                item = {
                    "stock_id": stock_id,
                    "name": stock_name,
                    "match_count": match_count,
                    "eps_4q": round(eps_4q, 2),
                    "margin": round(gross_margin, 2),
                    "operating_margin": round(operating_margin, 2),
                    "rev_yoy": round(rev_yoy_3m_avg, 2),
                    "capital": round(capital_billion, 2),
                    "major_holders": round(major_holder_ratio, 2)
                }
                candidates.append(item)
                print(f"🎯 [{idx}/{total_count}] 找到潛力股！[{match_count}/6 項符合] {stock_id} {stock_name} (EPS: {round(eps_4q,1)}, 大戶: {round(major_holder_ratio,1)}%)")

            # 每處理 100 檔輸出一次進度
            if idx % 100 == 0:
                total_count_str = len(stock_list) if 'total_count' not in locals() else total_count
                print(f"⏳ 已完成 {idx}/{total_count} 檔掃描...")

        except Exception as e:
            err_msg = str(e).lower()
            if "ip banned" in err_msg or "429" in err_msg:
                print(f"⚠️ 觸發 FinMind IP 頻率限制，觸發檔位 {stock_id}，自動冷卻 30 秒後繼續...")
                time.sleep(30)  # 👈 如果不幸已經被擋，自動冷卻 30 秒救回
            else:
                if is_debug:
                    print(f"❌ [DEBUG 報錯] {stock_id} 運算時發生例外錯誤: {e}")
            time.sleep(0.3)
        continue

    df_result = pd.DataFrame(candidates)
    if not df_result.empty:
        df_result = df_result.sort_values(by=["match_count", "major_holders", "eps_4q"], ascending=[False, False, False])
        
    return df_result

def generate_table_html(df_group, bg_color):
    """產生分級 HTML 表格"""
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
        print("⚠️ 未設定 Email 環境變數，跳過寄信步驟。")
        return

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    subject = f"🎯【千金預備軍分級巡檢】{today_str} 自動化月報"

    df_6 = df[df['match_count'] == 6] if not df.empty else pd.DataFrame()
    df_5 = df[df['match_count'] == 5] if not df.empty else pd.DataFrame()
    df_4 = df[df['match_count'] == 4] if not df.empty else pd.DataFrame()

    total_found = len(df) if not df.empty else 0

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <h2 style="color: #d9534f; border-bottom: 2px solid #d9534f; padding-bottom: 8px;">🔥【千金預備軍分級監控報告】🔥</h2>
        <p>機器人已完成全台股財報與籌碼掃描，本次共掃描出 <b>{total_found}</b> 檔符合 4 項（含）以上條件之標的：</p>

        <p><b>📋 當前2026 10月版『千金 6 大 DNA』篩選門檻如下：</b><br>
        1. 資本額小於 60 億（中小型股）<br>
        2. 近 4 季 EPS ≥ 12 元（一年賺 1 個股本）<br>
        3. 毛利率 ≥ 30%（極高獲利護城河）<br>
        4. 營益率 ≥ 15%（本業獲利極強）<br>
        5. 營收 YoY ≥ 10%（近 3 個月營收爆發）<br>
        6. 千張大戶持股 ≥ 50%（籌碼高度集中）</p>
        
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
