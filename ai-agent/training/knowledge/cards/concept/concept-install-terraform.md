# Concept: installing Terraform

deploy_docs/HOW_TO_INSTALL_TERRAFORM.md lists three ways to install Terraform on Windows. One is winget. One is Chocolatey, which needs an administrator shell. One is a manual zip download from the HashiCorp install page, unzipped into a folder that is then added to the user PATH. After a PATH change, open a new shell and run terraform -version.

The same doc says you can skip the PATH edit by setting PSKIT_TERRAFORM_BIN to the full path of terraform.exe. pskit doctor reports whether terraform or tofu can be found. The troubleshooting page says that when neither binary is on PATH, set PSKIT_TERRAFORM_BIN or provider.terraform.binary.

pskit does not call cloud APIs itself. It writes main.tf.json and runs terraform or tofu. OpenTofu is selected with PSKIT_TERRAFORM_BIN=tofu. A real install path from the doc was left out of this card.

```
pskit doctor
pskit validate
```

Run pskit doctor after the install so the studio Setup page and the terminal agree that a Terraform binary is available. Then pskit validate checks pskit.yml before any apply. The Deploy page in studio runs the same pipeline after you confirm.
