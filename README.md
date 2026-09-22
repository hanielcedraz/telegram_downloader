# Telegram Downloader

Aplicativo de desktop para baixar arquivos de grupos e canais do Telegram de
forma organizada — com análise prévia de tamanho, seleção por categoria e
pré-visualização das imagens antes de baixar.

---

## Instalação

Descompacte o arquivo e mantenha todos os arquivos **na mesma pasta**.

### macOS

Abra o Terminal na pasta descompactada e rode:

```bash
chmod +x instalar_mac.sh
./instalar_mac.sh
```

Ao final, um ícone aparece na área de trabalho e o app fica em
`/Applications`. Abra com duplo clique.

Se o macOS reclamar que o app é de desenvolvedor não identificado, clique com o
botão direito no ícone e escolha **Abrir** — só na primeira vez.

### Windows

Duplo clique em **`instalar_windows.bat`**.

Ao final, atalhos aparecem na área de trabalho e no menu Iniciar.

Se o Python não estiver instalado, o instalador abre a página de download.
Ao instalar o Python, marque as duas opções:

- **Add python.exe to PATH**
- **tcl/tk and IDLE** (em *Optional Features*)

---

## Primeiro uso

O app pede duas credenciais gratuitas do Telegram: **api_id** e **api_hash**.
A tela tem um botão que leva direto à página onde obtê-las. O caminho é:

1. Acesse `my.telegram.org`
2. Informe seu telefone com código do país (`+5571999999999`) — o código de
   acesso chega no próprio app do Telegram
3. Entre em **API development tools**
4. Preencha *App title* e *Short name* (qualquer nome), plataforma **Desktop**;
   URL e descrição podem ficar vazias
5. Clique em **Create application**
6. Copie *App api_id* e *App api_hash* para o aplicativo

Em seguida o app pede seu telefone e o código de login. A sessão fica salva —
esse passo só acontece uma vez.

> **Atenção:** essas credenciais são pessoais e dão acesso à sua conta.
> Não compartilhe com ninguém e não publique em repositórios.

> Ao pedir o código de login, **não abra a conversa** do Telegram onde ele
> chegou. O Telegram invalida códigos que foram lidos dentro do app. Copie
> pela notificação, ou peça um novo código.

---

## Como usar

**1. Grupos** — clique em *Carregar grupos* para listar tudo que você
participa. Também dá para colar um `@username` ou link e clicar em *Usar*.

**2. Análise** — cada grupo analisado abre numa **aba própria**, com seus
próprios dados, seleção e download. Dá para analisar vários grupos ao mesmo
tempo e alternar entre eles para comparar; o título da aba mostra ⏳ enquanto
analisa, ⬇ enquanto baixa e o tamanho total ao terminar. Feche pelo **×** da
aba ou com Cmd+W / Ctrl+W. Selecionar vários grupos na lista e clicar em
*Analisar* abre todos de uma vez.

A análise percorre o histórico lendo apenas metadados; nenhum arquivo é
baixado nessa etapa. O resultado é uma árvore:

```
▸ modelos-3d          1.240   14.2 GB
    ▸ .stl              890    9.8 GB
          suporte.stl              12.4 MB
          clip.stl  (dup)  🖼       3.1 MB
    ▸ .3mf              350    4.4 GB
▸ imagens             2.100    1.1 GB
```

Selecione em qualquer nível — uma categoria inteira, um tipo de arquivo, ou
itens avulsos com Ctrl/Cmd+clique. O rótulo mostra em tempo real quantos
arquivos e quantos GB a seleção representa, e o espaço livre no disco aparece
ao lado do campo de destino.

A lista pode ser vista **por categoria** ou **por modelo (nome parecido)**,
que junta versões e partes do mesmo modelo (`suporte_v2.stl`,
`suporte_final.3mf`, a foto do post) num só item. O campo *Buscar* filtra
por nome, sem precisar de acentos.

**3. Pré-visualização** — clicando num arquivo, o painel à direita mostra a
foto publicada no mesmo post, com legenda e data. O ícone 🖼 na lista indica
quais arquivos têm imagem disponível. *Selecionar todo o post* marca de uma vez
o modelo, as fotos e o que mais tiver vindo junto.

**4. Download** — escolha como organizar as pastas e clique em *Baixar
selecionados*.

| Modo | Resultado |
|---|---|
| Pasta única | `peca.stl` |
| Categoria | `modelos-3d/peca.stl` |
| Categoria / extensão | `modelos-3d/stl/peca.stl` |
| Extensão | `stl/peca.stl` |
| Ano-mês | `2026-07/peca.stl` |
| Ano-mês / categoria | `2026-07/modelos-3d/peca.stl` |

O botão *Reorganizar pasta destino* aplica o esquema escolhido a arquivos já
baixados anteriormente.

---

## Recursos

- **Retomar**: um registro do que já foi baixado fica na pasta de destino, então
  fechar o app no meio não custa nada — ao retomar, ele pula o que já existe.
- **Duplicatas**: arquivos com mesmo nome e tamanho são marcados com `(dup)` e
  podem ser ignorados. Em grupos de modelos 3D isso costuma poupar bastante
  espaço.
- **Flood wait**: o Telegram limita downloads em massa. O app detecta, espera o
  tempo pedido e continua sozinho.
- **Limite de mensagens**: o campo *Limite* permite analisar só as mensagens
  mais recentes, útil para uma estimativa rápida em grupos enormes.

---

## Onde ficam os arquivos

| | macOS | Windows |
|---|---|---|
| Configuração e sessão | `~/.tg_downloader/` | `%LOCALAPPDATA%\TelegramDownloader\` |
| Aplicativo | `/Applications/Telegram Downloader.app` | atalhos para o mesmo diretório |
| Log de erros | `~/.tg_downloader/erros.log` | console do Python |

Para desinstalar, apague essas pastas e os atalhos.

---

## Problemas comuns

**"macOS 14 (1408) or later required"** — o app foi aberto com o Python antigo
do sistema, que usa Tcl/Tk 8.5. Use o atalho criado pelo instalador em vez de
chamar `python3` no terminal.

**"You also need to provide a phone_code_hash"** — clique em *Enviar código*
antes de *Entrar*. Se reiniciou o app entre um passo e outro, peça o código de
novo.

**"ChatForwardsRestrictedError"** — o administrador do grupo ativou a restrição
de salvamento de conteúdo. Não há como contornar pela API.

**Downloads muito lentos** — instale o acelerador de criptografia:
`pip install pycryptodome` no ambiente do app. O instalador já tenta fazer isso
automaticamente.

---

## Requisitos

Python 3.9 ou superior, com Tcl/Tk 8.6. Os instaladores cuidam disso.
As bibliotecas usadas são `telethon` (obrigatória), `pillow` (miniaturas) e
`pycryptodome` (opcional, acelera a criptografia).

---

## Uso responsável

A automação de contas de usuário está sujeita às regras do Telegram. Downloads
em massa muito agressivos podem resultar em limitações temporárias na conta — o
intervalo entre arquivos existe justamente para reduzir esse risco.

Grupos de compartilhamento frequentemente incluem material com direitos
autorais, redistribuído sem autorização do criador. Baixar para uso pessoal é
uma coisa; revender peças impressas a partir de modelos pagos de terceiros, ou
redistribuir os arquivos, é outra bem diferente. Vale conferir a licença do que
for usado comercialmente.
