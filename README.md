# Agendamento Salão

Aplicativo de agendamento para salão de unhas, com catálogo de serviços, horários disponíveis, contas de clientes com histórico e painel administrativo.

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

## Contas de clientes

Clientes podem criar conta ou entrar pelos links públicos do site. A página única de entrada reconhece a cliente pelo e-mail e a dona pelo usuário `dona` com a senha administrativa configurada; após o login, abre a área correspondente. Agendamentos feitos enquanto a cliente está conectada aparecem em **Minha conta**. Agendamentos antigos e reservas feitas sem login não são associados automaticamente a uma conta.

O painel administrativo não tem link na navegação pública. A dona entra pela opção **Entrar** e não precisa digitar `/admin`.

## Operação e limites

- O banco padrão é SQLite. Mantenha uma única instância do serviço; para escalar para múltiplas instâncias, migre para PostgreSQL e configure um driver e migrações de esquema.
- A aplicação verifica `/healthz` para indicar disponibilidade e acesso ao banco.
- O sistema protege a reserva simultânea do mesmo horário usando uma transação de escrita no SQLite.
- O aviso pelo WhatsApp é manual; o cliente pode abrir a conversa pela confirmação do agendamento.
