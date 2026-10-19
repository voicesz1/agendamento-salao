# Aplicativo de agendamento do salão

## Funcionamento atual

A cliente escolhe serviço, dia, horário e forma de pagamento, informando nome e WhatsApp. Não cria conta nem confirma e-mail. Somente a dona entra com senha para administrar o salão. O painel é acessado pelo aplicativo Android administrativo ou diretamente pelo endereço do painel; não há atalho nas telas públicas. A proteção continua baseada na autenticação, no limite de tentativas e na verificação de requisições, independentemente da visibilidade do link.

O projeto usa FastAPI, páginas Jinja e SQLite, com opção de PostgreSQL. Catálogo, agenda de 21 dias, pausas, folgas, serviços e painel usam o mesmo servidor. O aplicativo instalável é um PWA. As variantes Android cliente e dona abrem esse servidor como Trusted Web Activity. O PWA também oferece instruções de instalação pelo Safari.

As rotas antigas de cadastro, entrada e verificação de clientes estão desativadas. Os registros e vínculos antigos foram preservados no banco para evitar perda de dados, mas não são usados para associar novas reservas ou liberar acesso por conta. A confirmação é privada à sessão do navegador que fez a reserva. Atualizar essa página não recria uma reserva.

## Visual e temas

O fundo é neutro claro, com superfícies brancas e vinho nas ações principais. A tipografia usa Manrope e DM Sans, com um detalhe serifado no título inicial. A página inicial reúne categorias e cartões com preço, duração e botão de agendar. No celular, a navegação inferior oferece início, agendar e serviços.

O botão de lua/sol alterna entre claro e escuro e salva a escolha neste navegador. A mesma preferência vale para catálogo, reserva e painel, incluindo a entrada da dona. O tema é aplicado antes do carregamento visual e se sincroniza entre abas. Se o armazenamento do navegador estiver bloqueado, a alternância continua funcionando na página atual.

No computador, o pagamento aparece ao lado do formulário. No celular, aparece após os dados da cliente. Horários escolhidos e formas de pagamento selecionadas têm contorno e contraste próprios. Consultas antigas de horários são interrompidas ao trocar a seleção; o servidor verifica novamente a disponibilidade antes de reservar.

## Fotos dos serviços

A dona pode adicionar uma foto ao criar o serviço ou enviar outra ao editar. A imagem aparece no cartão do catálogo. Há visualização da foto atual no painel e opção de removê-la. Serviços sem foto continuam visíveis e disponíveis normalmente.

São aceitas fotos JPG, PNG e WebP estáticas, de até 5 MB e 20 megapixels. O servidor valida o conteúdo, ajusta a orientação, reduz a imagem a no máximo 1600 pixels por lado e salva um JPEG sem metadados de câmera. Um arquivo inválido não altera o serviço nem substitui a foto existente. Uma nova foto tem prioridade se for enviada junto da opção de remover a atual.

As fotos ficam no próprio banco, junto dos serviços, e acompanham o backup. As migrações adicionam campos opcionais sem apagar o catálogo. A imagem é carregada sob demanda; a consulta da lista de serviços não precisa buscar todos os arquivos. Fotos de serviços inativos só são acessíveis à dona autenticada. Só a dona pode enviar, trocar ou remover fotos, com proteção contra requisições forjadas.

## Pix

O Pix usa conferência manual. A dona cadastra a chave e o titular. Sem esses dados, a opção fica indisponível e a cliente pode pagar no salão. A reserva guarda o valor em centavos e uma cópia dos dados do Pix, para que alterações posteriores não mudem a instrução já apresentada.

Pagamento e reserva têm estados independentes. **Pagar no estabelecimento** é a opção inicial, inclusive quando o salão tem Pix cadastrado. Nesse caso, a reserva é confirmada sem Pix e o pagamento será feito no atendimento. A cliente também pode escolher **Pix (opcional)**: copia a chave, abre o banco, informa o valor e confere o titular. Somente a dona pode registrar que conferiu o recebimento. Cancelar uma reserva não faz estorno automático. O horário fica reservado antes do pagamento, sem expiração automática.

## Reaproveitamento

| Componente | Site e aplicativo |
| --- | --- |
| Catálogo e fotos | Mesmo cadastro e armazenamento |
| Agenda e conflitos | Mesmas regras e banco |
| Reserva sem conta | Mesmo formulário e confirmação privada à sessão |
| Pix e recebimento | Mesmo valor registrado e controle da dona |
| Identidade e temas | Mesmos templates e estilo responsivo |
| Android cliente e dona | Mantêm a base TWA e abrem as telas correspondentes |

## Validação e limites

Quinze testes de integração passaram em SQLite descartável. Eles cobrem reserva sem cadastro, rotas de clientes desativadas, preservação de registros antigos, controle administrativo, Pix opcional e pagamento no estabelecimento, restrição da confirmação, proteção CSRF, envio e tratamento de fotos, substituição e remoção de imagens, arquivos inválidos e migrações repetidas.

O navegador foi usado para conferir o visual móvel e de computador, a alternância de tema, persistência após recarregar e navegação entre reserva e painel. Os testes não fizeram pagamentos nem enviaram notificações.

Nenhuma publicação, recompilação Android ou transação foi realizada. As alterações anteriores do manifesto, APK e arquivos do Android Studio foram preservadas. Ainda não houve teste em aparelho físico ou PostgreSQL. O aplicativo instalado só receberá as alterações depois da publicação autorizada do servidor.

Para habilitar o Pix manual, a dona deve cadastrar chave e titular. Para QR Code de cobrança e confirmação automática, ainda é necessário escolher um provedor e configurar credenciais, webhooks autenticados, expiração e reconciliação. Se o salão quiser exigir sinal, precisa definir valor e prazo.
