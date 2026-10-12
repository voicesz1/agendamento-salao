# Aplicativo Android (Trusted Web Activity)

Este diretório prepara o aplicativo Android que abre o site publicado como uma Trusted Web Activity. O app aponta para `https://agendamento-salao-e8gw.onrender.com` e usa o pacote inicial `com.atelierdasunhas.agendamento`.

## Preparar e compilar

1. Publique no Render as alterações do PWA e confirme que `/static/manifest.webmanifest` e os ícones estão acessíveis no endereço do salão.
2. Instale o Android Studio e, pelo SDK Manager, instale a plataforma Android 36 e o Android SDK Build-Tools. O projeto usa Java 17.
3. Se o SDK não estiver em `ANDROID_SDK_ROOT` ou `ANDROID_HOME`, crie `local.properties` com `sdk.dir=C:\\caminho\\para\\Android\\Sdk`.
4. Para criar a chave de envio, use a opção **Build → Generate Signed Bundle / APK → Android App Bundle** do Android Studio ou o `keytool` do JDK 17. A senha da chave não deve ser enviada ao GitHub.
5. Copie `keystore.properties.example` para `keystore.properties` e preencha os dados da chave localmente. Os dois arquivos sensíveis (`keystore.properties` e `android-upload-key.jks`) já são ignorados pelo Git.
6. No PowerShell, dentro desta pasta, execute:

   ```powershell
   .\build.ps1
   ```

O script baixa Gradle 8.11.1 e compila o Android App Bundle. Se `keystore.properties` estiver preenchido, o arquivo de saída já será assinado. Guarde a chave e a senha em local seguro; sem elas, não será possível publicar atualizações do mesmo app.

O identificador inicial é `com.atelierdasunhas.agendamento`. Confirme que ele está disponível antes da primeira publicação, pois o identificador do app não deve ser trocado depois.

## Associação do domínio

O app só abre sem a barra do navegador depois que a assinatura está associada ao domínio via Digital Asset Links. Após criar o app e ativar Play App Signing no Play Console, copie o SHA-256 do **certificado de assinatura do app** (não o certificado de upload). Configure no Render:

- `ANDROID_APP_PACKAGE`: `com.atelierdasunhas.agendamento`
- `ANDROID_APP_SHA256_CERT_FINGERPRINT`: SHA-256 no formato `AA:BB:...` fornecido pelo Play Console. É possível informar mais de uma impressão digital separando-as por vírgulas para validar versões de teste e produção.

O site publica o arquivo de associação em `/.well-known/assetlinks.json`. Depois do deploy, abra esse endereço e confirme que ele mostra o pacote e o fingerprint corretos antes de testar a TWA.

O pacote ainda precisa ser testado em Android Studio e enviado para uma faixa de teste na Play Console antes da publicação pública. O Google Play exige que novos apps enviados a partir de 31 de agosto de 2026 tenham como alvo Android 16 (API 36) ou superior; este projeto já está configurado com esse nível.
