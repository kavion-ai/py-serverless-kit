Before you start (once): upload ai-agent/hana_stage1_colab.zip from your PC to My Drive (the top level) at drive.google.com.

---

Cell 1: mount Google Drive

from google.colab import drive
drive.mount("/content/drive")
Sign in with the account where you uploaded the zip.

Cell 2: check Drive, unzip, fix torchao

!test -d /content/drive/MyDrive && echo "DRIVE OK" || echo "DRIVE NOT MOUNTED - run cell 1"
!ls /content/drive/MyDrive/
!mkdir -p /content/drive/MyDrive/hana
%cd /content
!unzip -o -q /content/drive/MyDrive/hana_stage1_colab.zip -d /content/
!pip uninstall -y torchao
!ls /content/training/train
You must see DRIVE OK, hana_stage1_colab.zip in the list, and step1…step6 at the end.

Cell 3: check the environment

!python ./training/train/step1_env_check.py

Cell 4: tokenize the data (about 2 min)

!DATA=final_v2 python ./training/train/step2_prepare.py

Cell 5: smoke test (about 5 min, saves nothing)

!SMOKE=1 python ./training/train/step3_train.py
Look for the [speed] line and make sure there's no error.

Cell 6: real training (about 3 h 45 min, saves to Drive)

!OUTPUT_DIR=/content/drive/MyDrive/hana/stage1_v2 EPOCHS=3 python ./training/train/step3_train.py
Keep the browser tab open.

If Colab disconnects: run cells 1, 2 and 4 again, then cell 6 again. It continues from the last saved checkpoint, so nothing is lost.

Cell 7: check that the adapter is on Drive


Cell 11: backup copy for your PC (recommended)

!cd /content/drive/MyDrive && zip -r -0 hana_backup_small.zip hana -x "*/checkpoint-*"
!ls -lh /content/drive/MyDrive/hana_backup_small.zip
Then on drive.google.com, right-click hana_backup_small.zip and choose Download. Keep it outside the git repo.

---

I skipped the evaluation step (step 4) because it's the same data and settings as before. If you want the scores, run this after cell 7:
!DATA=final_v2 ADAPTER=/content/drive/MyDrive/hana/stage1_v2/adapter_final python ./training/train/step4_eval.py

Paste me the output after cell 5, then after cells 6 and 8.