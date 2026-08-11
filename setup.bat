@echo off
echo Creating virtual environment...
if not exist .venv (
	python -m venv .venv
)

echo Activating virtual environment...

call .venv/Scripts/activate

REM Upgrade pip first seperately
python -m pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org


REM Install dependencies with trusted host to prevent SSL errors
echo Installing dependencies from requirements.txt
pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org

REM Create necessary folder if they don't exist
if not exist input_images (
	mkdir input_images
)

if not exist output_images (
	mkdir output_images
)

if not exist styled_images (
	mkdir styled_images
)

echo input_images, output_images and styled_images folder were created if not present already

echo Setup complete, this window closes automatically. Launch doodle_photobooth.bat to start the application
timeout /t 10 >nul