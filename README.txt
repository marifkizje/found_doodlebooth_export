#DESCRIPTION OF THE PROJECT
The AI doodle photobooth is a project developed for the Data Expo. 
It allows users to take a photo, transform it with AI based on a predefined prompt, 
style it with BearingPoint branding, and print it.

#WORKFLOW
1. Take a photo of the doodle (manual)
2. Transfer photo to input folder
3. Encode photo and call model API
4. Receive response
5. Decode image
6. Save image
7. Add BearingPoint branding
8. Send image to printer for printing

#FOLDER STRUCTURE
doodle_photobooth_app
|
|--.venv/ #virtual environment
|--.vscode/ #vscode settings.json for explicit interpreter path definition.
|--input_images/ #input images folder
|--output_images/ #output image FOLDER
|--environment_variables.env
|--main.py
|--README.text
|--requirements.txt
|--setup.bat

#HOW TO USE
1. Run setup.bat, this might take a couple of minutes.
2. After running setup.bat, check if folders were created as shown in the folder structure above, if not rerun setup.bat again or create folder manually
3. Click on canaon_EOS_euw3.19.0.12-installer.exe, click through all the steps.
4. Open EOS application and [WRITE OUT FOLLOW UP STEPS]
5. Double click doodle_photobooth.bat or run from CLI. When successful it will return "Started monitoring folder: {folder}"
6. Take a photo to activate the workflow. It will continue to monitor the folder for new photos until interrupted. 
7. To stop the script press Ctrl + c and when prompted to Terminate batch job (Y/N)? type "Y" and press enter
