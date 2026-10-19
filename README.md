<<<<<<< HEAD
# Agendamento Salão

Aplicativo de agendamento para salão de unhas, com catálogo ilustrado, horários disponíveis, Pix com conferência manual e painel administrativo. A cliente agenda informando nome e WhatsApp, sem conta ou senha. Somente a dona faz login para administrar o salão.

## Executar localmente

Requer Python 3.10 ou mais recente.

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abra <http://127.0.0.1:8000>. O primeiro acesso local ao painel (`/admin`) usa a senha `admin123`; troque-a em **Configurações** antes de publicar o site.

## Implantar com Docker

O Compose inicia o serviço com SQLite persistente e um único processo, adequado ao volume esperado de um salão pequeno. O site deve ficar atrás de um proxy reverso com HTTPS (por exemplo, Caddy, Nginx ou o proxy do provedor). A porta do contêiner fica disponível apenas em `127.0.0.1:8000` no servidor.

1. Copie `.env.example` para `.env` e defina segredos diferentes e aleatórios para `SECRET_KEY` e `ADMIN_PASSWORD`. A senha precisa ter pelo menos 12 caracteres.
2. Inicie com `docker compose up -d --build`.
3. Configure o proxy HTTPS para encaminhar para `127.0.0.1:8000`.
4. Configure os dados, horários, serviços e WhatsApp no painel administrativo.

O contêiner recusa iniciar em produção se os segredos estiverem ausentes ou forem fracos. A sessão administrativa usa cookie seguro, SameSite estrito, proteção CSRF e limite de tentativas de login. A URL de documentação da API fica desativada em produção.

Os dados ficam no volume Docker `salao_data`. Faça backups regulares desse volume e teste a restauração; para SQLite, pare o serviço antes de copiar o arquivo `salao.db`.

## WhatsApp

Em **Configurações**, cadastre o número da dona com DDI. Na confirmação do agendamento, o link abre o WhatsApp com a mensagem pronta para envio manual.

## Acesso da dona e reserva sem conta

A cliente escolhe serviço, dia, horário e pagamento, informando somente nome e WhatsApp. Não há cadastro, login de cliente, histórico de conta ou confirmação de e-mail. A dona entra diretamente em `/admin` ou pelo aplicativo Android administrativo. As telas públicas não exibem atalho para o painel; ele continua protegido por senha, limite de tentativas e proteção CSRF.

As rotas antigas de contas de clientes estão desativadas. Dados e vínculos antigos permanecem preservados no banco, mas não são usados para preencher ou vincular novas reservas. O módulo antigo de e-mail não é necessário para agendar.

## Fotos nos serviços

Em **Painel administrativo → Serviços**, escolha uma foto ao criar um serviço ou use **Adicionar foto ilustrativa/Trocar foto** em um serviço existente. Salve para exibir a imagem no catálogo. Serviços sem foto continuam funcionando normalmente. É possível remover a foto marcando a opção correspondente e salvando sem enviar uma nova.

Aceita JPG, PNG e WebP estáticos, de até 5 MB e 20 megapixels. O servidor valida o conteúdo, ajusta a orientação, limita a imagem a 1600 pixels por lado e a transforma em JPEG sem metadados de câmera. Arquivos inválidos não substituem a foto anterior nem alteram os dados do serviço.

As imagens ficam no próprio banco de dados, junto dos serviços, e entram no mesmo backup. Não dependem de uma pasta temporária de uploads. A atualização adiciona campos opcionais sem apagar o catálogo ou as reservas. Para serviços inativos, a foto só fica acessível à dona autenticada.

## Operação e limites

### Pagamento Pix

Em **Painel → Configurações → Receber por Pix**, cadastre a chave copiada do banco e o nome do titular. Sem os dois campos, o Pix fica indisponível e a cliente pode escolher pagar no salão. O cadastro não valida a chave nem a titularidade no banco.

Ao reservar, a cliente escolhe **Pix** ou **No salão**. O valor em centavos e, no caso do Pix, a chave e o titular são gravados na reserva. Alterar o catálogo ou a chave depois não altera esses dados nas reservas existentes. Reservas antigas continuam preservadas; valores que não foram registrados na época não são reconstruídos a partir do preço atual.

Na confirmação, **Copiar chave Pix** copia somente a chave: a cliente abre o banco, informa o valor e confere o titular. Não há QR Code, código Pix Copia e Cola de cobrança, conexão bancária ou confirmação automática. O status começa como **pendente**. A dona confere o recebimento no banco, marca **Conferi o recebimento** no painel e registra o pagamento. Cancelar a reserva não estorna o pagamento e não apaga um recebimento registrado.

O horário é reservado independentemente do pagamento, sem prazo de expiração. Reservas pendentes continuam ocupando a agenda até serem canceladas no painel. Não há exigência de sinal nem cobrança de taxa. Para exigir pré-pagamento, gerar cobranças com vencimento e confirmar automaticamente, ainda é necessário escolher um provedor Pix, configurar credenciais no servidor e implementar webhooks autenticados, idempotência e reconciliação. Nenhuma credencial de provedor foi adicionada.

<<<<<<< HEAD
### Cartão pelo Mercado Pago (Checkout Pro)

O checkout hospedado no Mercado Pago recebe os dados do cartão; o aplicativo não guarda número, validade ou código de segurança. A opção só aparece quando `MERCADOPAGO_ACCESS_TOKEN`, `MERCADOPAGO_WEBHOOK_SECRET` e uma `PUBLIC_BASE_URL` HTTPS estão configurados. Em **Vercel → projeto → Settings → Environment Variables**, adicione:

- `MERCADOPAGO_ACCESS_TOKEN`: Access Token de teste enquanto valida a integração; nunca use a Public Key neste campo.
- `MERCADOPAGO_WEBHOOK_SECRET`: chave secreta de assinatura criada para a notificação Webhook no Mercado Pago. Ela é diferente do Access Token.
- `PUBLIC_BASE_URL`: `https://crys-nail-designers.vercel.app`.

No painel do Mercado Pago Developers, configure uma notificação Webhook HTTPS para `https://crys-nail-designers.vercel.app/webhooks/mercadopago` e marque o evento **Pagamentos**. Copie a chave secreta de assinatura dessa notificação para `MERCADOPAGO_WEBHOOK_SECRET`. O webhook confere a assinatura e consulta o pagamento diretamente na API do Mercado Pago antes de marcar a reserva como paga. A volta do checkout ao navegador, sozinha, não confirma pagamento.

Depois de salvar as variáveis no Vercel, faça um novo deployment para elas entrarem em vigor. Comece com credenciais de teste e pagamentos de teste; para aceitar pagamentos reais, troque pelo Access Token de produção somente depois de validar e publicar a configuração de produção. Não envie tokens ou segredos por chat, nem os grave no Git. Reservas de cartão não aprovadas também ocupam o horário até que sejam canceladas no painel; não há expiração automática.

=======
>>>>>>> 7ec44561c7d98161acfc38f2b2a0b4a3459d0045
A confirmação usa um endereço GET para evitar criar uma nova reserva ao atualizar a página. Seu acesso é restrito à sessão que fez a reserva (as dez mais recentes). Guarde os dados: o endereço não serve como link público de compartilhamento e deixa de funcionar após encerrar a sessão. As páginas de reserva e pagamento não são armazenadas pelo service worker ou pelo cache HTTP.

### Verificação local

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Os testes criam um SQLite descartável, separado dos dados do salão, e cobrem preço e chave preservados, acesso à confirmação, CSRF, agenda ocupada, ausência de contas de clientes, conferência administrativa, envio de fotos e migrações que preservam os dados existentes. Não enviam pagamentos ou notificações.

### Instalar no Android

O site pode ser instalado como aplicativo PWA sem publicar na Play Store. Quando o Chrome considerar o site instalável, uma janela oferecerá a instalação; a pessoa precisa tocar em **Instalar agora** para abrir a confirmação nativa do Android. O botão **Instalar app** também fica disponível no cabeçalho. Se a janela não aparecer, use o menu ⋮ do Chrome → **Instalar app** ou **Adicionar à tela inicial**. O app usa o mesmo site e precisa de internet para consultar horários e fazer agendamentos. Por segurança, páginas de login e agendamento não são armazenadas para uso offline.

Para gerar a versão para a Play Store, consulte [android/README.md](android/README.md). Ela usa uma Trusted Web Activity vinculada ao mesmo site.

- O banco padrão é SQLite. Mantenha uma única instância do serviço; para escalar para múltiplas instâncias, migre para PostgreSQL e configure um driver e migrações de esquema.
- A aplicação verifica `/healthz` para indicar disponibilidade e acesso ao banco.
- O sistema protege a reserva simultânea do mesmo horário usando uma transação de escrita no SQLite.
- O aviso pelo WhatsApp é manual; o cliente pode abrir a conversa pela confirmação do agendamento.
- A cliente não cria conta. Somente a dona usa login e senha no painel. A confirmação da reserva fica disponível apenas durante a sessão no navegador que a criou.
=======
# Agendamento Salão

Aplicativo de agendamento para salão de unhas, com catálogo ilustrado, horários disponíveis, Pix com conferência manual e painel administrativo. A cliente agenda informando nome e WhatsApp, sem conta ou senha. Somente a dona faz login para administrar o salão.

## Executar localmente

Requer Python 3.10 ou mais recente.

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abra <http://127.0.0.1:8000>. O primeiro acesso local ao painel (`/admin`) usa a senha `admin123`; troque-a em **Configurações** antes de publicar o site.

## Implantar com Docker

O Compose inicia o serviço com SQLite persistente e um único processo, adequado ao volume esperado de um salão pequeno. O site deve ficar atrás de um proxy reverso com HTTPS (por exemplo, Caddy, Nginx ou o proxy do provedor). A porta do contêiner fica disponível apenas em `127.0.0.1:8000` no servidor.

1. Copie `.env.example` para `.env` e defina segredos diferentes e aleatórios para `SECRET_KEY` e `ADMIN_PASSWORD`. A senha precisa ter pelo menos 12 caracteres.
2. Inicie com `docker compose up -d --build`.
3. Configure o proxy HTTPS para encaminhar para `127.0.0.1:8000`.
4. Configure os dados, horários, serviços e WhatsApp no painel administrativo.

O contêiner recusa iniciar em produção se os segredos estiverem ausentes ou forem fracos. A sessão administrativa usa cookie seguro, SameSite estrito, proteção CSRF e limite de tentativas de login. A URL de documentação da API fica desativada em produção.

Os dados ficam no volume Docker `salao_data`. Faça backups regulares desse volume e teste a restauração; para SQLite, pare o serviço antes de copiar o arquivo `salao.db`.

## WhatsApp

Em **Configurações**, cadastre o número da dona com DDI. Na confirmação do agendamento, o link abre o WhatsApp com a mensagem pronta para envio manual.

## Acesso da dona e reserva sem conta

A cliente escolhe serviço, dia, horário e pagamento, informando somente nome e WhatsApp. Não há cadastro, login de cliente, histórico de conta ou confirmação de e-mail. A dona entra diretamente em `/admin` ou pelo aplicativo Android administrativo. As telas públicas não exibem atalho para o painel; ele continua protegido por senha, limite de tentativas e proteção CSRF.

As rotas antigas de contas de clientes estão desativadas. Dados e vínculos antigos permanecem preservados no banco, mas não são usados para preencher ou vincular novas reservas. O módulo antigo de e-mail não é necessário para agendar.

## Fotos nos serviços

Em **Painel administrativo → Serviços**, escolha uma foto ao criar um serviço ou use **Adicionar foto ilustrativa/Trocar foto** em um serviço existente. Salve para exibir a imagem no catálogo. Serviços sem foto continuam funcionando normalmente. É possível remover a foto marcando a opção correspondente e salvando sem enviar uma nova.

Aceita JPG, PNG e WebP estáticos, de até 5 MB e 20 megapixels. O servidor valida o conteúdo, ajusta a orientação, limita a imagem a 1600 pixels por lado e a transforma em JPEG sem metadados de câmera. Arquivos inválidos não substituem a foto anterior nem alteram os dados do serviço.

As imagens ficam no próprio banco de dados, junto dos serviços, e entram no mesmo backup. Não dependem de uma pasta temporária de uploads. A atualização adiciona campos opcionais sem apagar o catálogo ou as reservas. Para serviços inativos, a foto só fica acessível à dona autenticada.

## Operação e limites

### Pagamentos

Além do pagamento no salão e do Pix manual, a cliente pode escolher **Cartão de crédito**. O app cria uma sessão do Checkout Pro e redireciona a cliente ao Mercado Pago; os dados do cartão não passam pelo servidor do salão. A reserva só fica marcada como paga depois que um webhook assinado é validado e o pagamento é consultado diretamente na API do Mercado Pago.

Para habilitar o cartão, configure no Vercel, em Production, `MERCADOPAGO_ACCESS_TOKEN`, `MERCADOPAGO_WEBHOOK_SECRET` e `PUBLIC_BASE_URL` (o endereço HTTPS público do app). Use o token de produção para cobranças reais. Tokens `TEST-` usam o checkout de teste. O cartão aparece desabilitado até que as três configurações estejam presentes.

### Pix manual

Em **Painel → Configurações → Receber por Pix**, cadastre a chave copiada do banco e o nome do titular. Sem os dois campos, o Pix fica indisponível e a cliente pode escolher pagar no salão. O cadastro não valida a chave nem a titularidade no banco.

Ao reservar, a cliente escolhe **Pix**, **Cartão de crédito** ou **No salão**. O valor em centavos e, no caso do Pix, a chave e o titular são gravados na reserva. Alterar o catálogo ou a chave depois não altera esses dados nas reservas existentes. Reservas antigas continuam preservadas; valores que não foram registrados na época não são reconstruídos a partir do preço atual.

Na confirmação, **Copiar chave Pix** copia somente a chave: a cliente abre o banco, informa o valor e confere o titular. Não há QR Code, código Pix Copia e Cola de cobrança, conexão bancária ou confirmação automática. O status começa como **pendente**. A dona confere o recebimento no banco, marca **Conferi o recebimento** no painel e registra o pagamento. Cancelar a reserva não estorna o pagamento e não apaga um recebimento registrado.

O horário é reservado independentemente do pagamento, sem prazo de expiração. Reservas pendentes continuam ocupando a agenda até serem canceladas no painel. No cartão, pagamentos recusados ou abandonados também deixam a reserva ativa até a dona cancelá-la. O Mercado Pago atualiza a situação do cartão por webhook; o cancelamento do horário não realiza estorno automático.

A confirmação usa um endereço GET para evitar criar uma nova reserva ao atualizar a página. Seu acesso é restrito à sessão que fez a reserva (as dez mais recentes). Guarde os dados: o endereço não serve como link público de compartilhamento e deixa de funcionar após encerrar a sessão. As páginas de reserva e pagamento não são armazenadas pelo service worker ou pelo cache HTTP.

### Verificação local

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Os testes criam um SQLite descartável, separado dos dados do salão, e cobrem preço e chave preservados, acesso à confirmação, CSRF, agenda ocupada, ausência de contas de clientes, conferência administrativa, envio de fotos e migrações que preservam os dados existentes. Não enviam pagamentos ou notificações.

### Instalar no Android

O site pode ser instalado como aplicativo PWA sem publicar na Play Store. Quando o Chrome considerar o site instalável, uma janela oferecerá a instalação; a pessoa precisa tocar em **Instalar agora** para abrir a confirmação nativa do Android. O botão **Instalar app** também fica disponível no cabeçalho. Se a janela não aparecer, use o menu ⋮ do Chrome → **Instalar app** ou **Adicionar à tela inicial**. O app usa o mesmo site e precisa de internet para consultar horários e fazer agendamentos. Por segurança, páginas de login e agendamento não são armazenadas para uso offline.

Para gerar a versão para a Play Store, consulte [android/README.md](android/README.md). Ela usa uma Trusted Web Activity vinculada ao mesmo site.

- O banco padrão é SQLite. Mantenha uma única instância do serviço; para escalar para múltiplas instâncias, migre para PostgreSQL e configure um driver e migrações de esquema.
- A aplicação verifica `/healthz` para indicar disponibilidade e acesso ao banco.
- O sistema protege a reserva simultânea do mesmo horário usando uma transação de escrita no SQLite.
- O aviso pelo WhatsApp é manual; o cliente pode abrir a conversa pela confirmação do agendamento.
- A cliente não cria conta. Somente a dona usa login e senha no painel. A confirmação da reserva fica disponível apenas durante a sessão no navegador que a criou.
>>>>>>> 18a17922f68412df42a435d3021fd4f1037c0346
