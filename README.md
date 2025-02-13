i-bidder Data Analysis Application Installation Guide
===============================================

1. Required Software Installation
-------------------------------

a) Python Installation:
- Go to https://www.python.org/downloads/
- Click "Download Python 3.11" button
- Run the downloaded file
- Check "Add Python to PATH" during installation
- Click "Install Now" to complete installation

2. Application Installation
-------------------

a) Download Application:
- Click Download zip option
- Extract downloaded file to desktop

b) Program Installation:
- Type "cmd" in Windows search bar and open Command Prompt
- Type following commands and press Enter:
  ```cd <path where you extracted the application>```
  ```pip install -r requirements.txt```

3. Running the Program
---------------------

a) For Each Launch:
- Open Command Prompt
- ```streamlit run homeview.py```

b) When Program Opens:
- A page will automatically open in your browser
- If it doesn't open, go to: http://localhost:8501

4. Important Notes
---------------

- You need to repeat step 3(a) every time you want to run the program
- Don't close Command Prompt window while program is running
- You can close browser page, use http://localhost:8501 to reopen

5. Common Issues
---------------------------

a) "Python was not found" error:
- Reinstall Python
- Make sure "Add Python to PATH" is checked

b) Page doesn't open:
- Check Command Prompt for error messages
- Close program and repeat step 3

c) "pip is not recognized" error:
- Uninstall Python
- Reinstall and check "Add Python to PATH"

d) "requirements.txt not found" error:
- Make sure you're in correct directory
- Run cd desktop\i-bidder-analyzer command again


Note: This program requires internet connection. Please ensure you have a stable internet connection.
