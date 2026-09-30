import time
import os
import pyautogui
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def run_automation():
    # -------------------------------------------------------------
    # Cấu hình Chrome Driver (Giữ đăng nhập Google Sheets nếu cần)
    # -------------------------------------------------------------
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    
    # Bỏ comment 2 dòng dưới nếu bạn muốn dùng Chrome Profile sẵn có để đã đăng nhập Google
    # user_data_dir = os.path.join(os.environ['USERPROFILE'], 'AppData', 'Local', 'Google', 'Chrome', 'User Data')
    # options.add_argument(f"user-data-dir={user_data_dir}")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 15) # Thời gian chờ tối đa 15s cho mỗi phần tử

    try:
        # 1. Mở trình duyệt, truy cập http://inside.fpt.net
        print("1. Truy cập http://inside.fpt.net")
        driver.get("http://inside.fpt.net")

        # 2. Nhập UserName
        print("2. Nhập UserName...")
        user_input = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="fUserName"]')))
        user_input.clear()
        user_input.send_keys("Bangnc13")

        # 3. Nhập Password
        print("3. Nhập Password...")
        pass_input = driver.find_element(By.XPATH, '//*[@id="fPassword"]')
        pass_input.clear()
        pass_input.send_keys("Thang09@2026")

        # 4. Bấm nút đăng nhập
        print("4. Bấm nút đăng nhập...")
        login_btn = driver.find_element(By.XPATH, '/html/body/div[2]/form/div/div/div[4]/a')
        login_btn.click()

        # 5. Bấm nút li[28]
        print("5. Bấm danh mục...")
        wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/div/ul/li[28]/div/a/img'))).click()

        # 6. Bấm nút sub-menu 1
        print("6. Bấm menu con 1...")
        wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/div/ul/li[28]/ul/li[1]/div/a/img'))).click()

        # 7. Bấm menu con 2
        print("7. Bấm menu con 2...")
        wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/div/ul/li[28]/ul/li[1]/ul/li[1]/div/a'))).click()

        # 8. Chờ 5s
        print("8. Chờ 5s...")
        time.sleep(5)

        # 9. Bấm nút SVG
        print("9. Click icon SVG...")
        wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/app/div[3]/div[2]/div/div/div[3]/div/div[4]/div/div/div/div/div[1]/div[2]/svg'))).click()

        # 10. Click đoạn văn p
        print("10. Click phần tử p...")
        wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/app/div[1]/div[8]/div/div[2]/div[2]/p'))).click()

        # 11. Bấm div lựa chọn
        print("11. Bấm div...")
        wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/app/div[3]/div[2]/div/div/div[4]/div/div/div[1]/div/div/div/div[2]/div'))).click()

        # 12. Bấm nút tìm kiếm / lọc (button index 43)
        print("12. Bấm nút tìm kiếm...")
        wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/app/div[3]/div[1]/div/div/div[2]/div/div/div/div/div[43]/button/span/p'))).click()

        # 13. Bấm link trong bảng
        print("13. Bấm link dữ liệu...")
        wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/app/div[3]/div[2]/div/div[2]/div[1]/div/div/div/div/table/tbody/tr/td[11]/span/a'))).click()

        # 14. Bấm nút Xuất/Tải xuống
        print("14. Bấm nút tải xuống...")
        wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/app/div[3]/div[2]/div/div[2]/div[8]/div/div/div[1]/button/span/strong'))).click()

        # 15. Xử lý Popup OK
        print("15. Bấm nút OK trên popup...")
        # Thử chấp nhận JavaScript Alert nếu có, hoặc click nút OK HTML
        try:
            WebDriverWait(driver, 3).until(EC.alert_is_present())
            driver.switch_to.alert.accept()
        except:
            # Nếu popup là HTML element: tìm nút chứa chữ OK
            ok_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'OK') or contains(., 'OK')]")))
            ok_btn.click()

        # 16. Mở danh sách tải về của Trình duyệt (Ctrl + J) và mở File Excel vừa tải
        print("16. Mở danh sách tải về (Ctrl + J)...")
        time.sleep(3) # Chờ file tải hoàn tất
        pyautogui.hotkey('ctrl', 'j')
        time.sleep(2)

        # Bấm Enter để mở file trên cùng vừa tải về trong Tab Downloads
        print("17. Mở file Excel trên cùng...")
        pyautogui.press('tab')
        pyautogui.press('enter')
        time.sleep(5) # Chờ Excel mở lên

        # 18. Coppy toàn bộ dữ liệu trong Excel (Ctrl + A -> Ctrl + C)
        print("18. Copy toàn bộ dữ liệu Excel...")
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(1)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(2)

        # 19. Truy cập vào Google Sheets
        sheets_url = "https://docs.google.com/spreadsheets/d/1qKW7OcGegD1IXcgV5WYXuzcUzYvpjZw-CqgzpYDLKoM/edit?pli=1&gid=0#gid=0"
        print(f"19. Truy cập Google Sheets: {sheets_url}")
        driver.get(sheets_url)

        # 20. Chờ 10s cho Google Sheets load xong hoàn toàn
        print("20. Chờ 10s...")
        time.sleep(10)

        # 21. Click vào trang tính và Dán dữ liệu (Ctrl + V)
        print("21. Dán dữ liệu (Ctrl + V)...")
        # Click vào vùng làm việc của Google Sheet
        pyautogui.click(x=500, y=500) 
        time.sleep(1)
        pyautogui.hotkey('ctrl', 'v')

        # 22. Chờ 5s
        print("22. Chờ 5s...")
        time.sleep(5)

        # 23. Lưu (Ctrl + S)
        print("23. Lưu dữ liệu (Ctrl + S)...")
        pyautogui.hotkey('ctrl', 's')
        time.sleep(2)

        print("---> KẾT THÚC CHƯƠNG TRÌNH THÀNH CÔNG! <---")

    except Exception as e:
        print(f"Có lỗi xảy ra trong quá trình chạy: {e}")
    finally:
        # Giữ trình duyệt mở thêm vài giây trước khi đóng
        time.sleep(5)
        driver.quit()

if __name__ == "__main__":
    run_automation()
