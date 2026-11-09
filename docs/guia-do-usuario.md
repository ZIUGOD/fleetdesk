# Guia do usuário do FleetDesk

O FleetDesk lê as planilhas de fretes que a empresa já preenche e mostra tudo em um painel:
faturamento, viagens, fechamento da folha, ajustes e uma auditoria que aponta possíveis
erros nas planilhas. Ele **não altera as planilhas**: você continua lançando os dados no Excel
como sempre, e o FleetDesk só lê.

**Baixar:** <https://ziugod.github.io/fleetdesk/>

---

## 1. O que você precisa

| Item | Detalhe |
|---|---|
| Computador | Windows 10 ou 11, 64 bits |
| Espaço em disco | Cerca de 60 MB |
| Internet | Só para baixar e para atualizar. O FleetDesk funciona sem internet |
| Planilhas | No modelo **FRETES (V2)**, com a aba `LANÇAMENTOS`. Uma planilha por mês funciona normalmente |
| Google Drive (opcional) | Se as planilhas ficam no Drive, instale o **Google Drive para computador** para que a pasta apareça no Windows |

Não é preciso instalar Python, nem ser administrador do computador.

## 2. Instalar (uma vez só)

1. Na página de download, clique em **Baixar instalador para Windows**.
2. Na pasta **Downloads**, dê dois cliques em `FleetDesk-Setup.exe`.
3. Se aparecer **"O Windows protegeu o computador"**, clique em **Mais informações** e depois em
   **Executar assim mesmo**. *O aviso aparece porque o instalador ainda não tem assinatura
   digital (está em andamento).*
4. Clique em **Avançar** e **Instalar**.

O FleetDesk abre sozinho no navegador e ganha um ícone na **Área de Trabalho** e no **menu
Iniciar**. A partir daí, use sempre esse ícone.

### Se o Windows bloquear o instalador sem a opção "Executar assim mesmo"

Isso acontece em computadores com o **Controle Inteligente de Aplicativos** ligado. Use a
**versão portátil**, que funciona nesses computadores porque todo programa dentro dela é
assinado digitalmente pela Python Software Foundation:

1. Na página de download, clique em **versão portátil (.zip)**.
2. Clique com o botão direito em `FleetDesk-windows.zip` > **Propriedades**, marque
   **Desbloquear** e clique em **OK**.
3. Clique de novo com o botão direito > **Extrair tudo...** e escolha uma pasta fixa, por
   exemplo **Documentos**. Não abra o FleetDesk de dentro do `.zip`.
4. Na pasta extraída, dê dois cliques em **Iniciar FleetDesk**. Ele cria o ícone na Área de
   Trabalho.

## 3. Primeiro uso

Na primeira vez, o FleetDesk abre em **Configurações**:

1. Em **Fonte de dados**, clique em **Escolher pasta...** e selecione a pasta onde ficam as
   planilhas de fretes (por exemplo, a pasta do Google Drive, que aparece como `G:\Meu Drive\...`).
   Se usar uma planilha só, clique em **Escolher planilha...**.
2. Confira a lista **Planilhas lidas**: cada planilha aparece como *Lida*, *Ignorada* (formato
   diferente) ou *Erro ao ler*.
3. Em **Empresa**, digite o nome da empresa.
4. Em **Aparência**, escolha tema claro, escuro ou automático.

Pronto: clique em **Dashboard**.

## 4. Uso no dia a dia

- **O FleetDesk relê as planilhas sozinho** sempre que alguém as salva. Não precisa reiniciar.
  Use **Recarregar** no menu se quiser forçar uma nova leitura.
- **Filtros:** em quase todas as telas dá para filtrar por competência (o período de 26 a 25),
  motorista, cliente e material.
- **Telas:**

| Tela | Para que serve |
|---|---|
| Dashboard | Faturamento, produção líquida, resultado, volume e gráficos |
| Auditoria | Possíveis erros nas planilhas, com a linha exata para conferir |
| Fretes | Todas as viagens, com filtros |
| Combustível | Abastecimentos, consumo e preço por litro |
| Fechamento | Produção, comissão, ajustes e total a pagar de cada motorista |
| Ajustes de folha | O que cada motorista faturou ao lado dos descontos e acréscimos |

- **Fechar o navegador não desliga o FleetDesk.** Ele continua rodando em segundo plano, sem
  pesar no computador. Para desligar de vez: **Configurações > Encerrar FleetDesk**.

## 5. Auditoria e resumo com IA

A tela **Auditoria** confere as planilhas automaticamente e mostra, para cada problema, **o
arquivo, a aba e a linha** para corrigir. Exemplos do que ela encontra:

- peso provavelmente digitado errado (vírgula no lugar errado);
- valor por tonelada muito diferente do normal para aquela rota;
- possível viagem lançada em duplicidade;
- desconto de folha lançado como crédito;
- o mesmo cliente escrito de dois jeitos (o que divide os totais nos gráficos);
- meses sem lançamentos de combustível ou pedágio.

Os achados são **pistas para conferir**, não certezas: alguns podem estar corretos (um preço
negociado diferente, por exemplo).

**Resumo com IA (opcional e gratuito).** O botão **Gerar resumo** usa uma inteligência
artificial que roda **no próprio computador**: nenhum dado vai para a internet. Para ativar:

1. Instale o **Ollama** em <https://ollama.com> (gratuito).
2. Abra o **Prompt de Comando** e digite: `ollama pull qwen2.5:3b` (baixa cerca de 2 GB).
3. Volte à Auditoria e clique em **Gerar resumo**. Leva de 5 a 30 segundos.

Computadores com pouca memória (menos de 8 GB) podem ficar lentos com a IA. Sem ela, a
Auditoria funciona do mesmo jeito, só sem o resumo.

## 6. Atualizar para uma versão nova

Ao abrir, o FleetDesk confere se existe uma versão nova. Se existir, aparece no topo da tela o
aviso **"Nova versão disponível"**:

1. Clique em **Atualizar agora**.
2. Espere alguns segundos: o FleetDesk baixa a versão nova, confere se o arquivo veio inteiro,
   fecha e abre de novo sozinho.

Suas configurações (pasta das planilhas, nome da empresa, tema) são mantidas. Para conferir na
hora, use **Configurações > Atualizações > Verificar agora**.

Raramente, uma versão troca o Python interno do FleetDesk e não pode ser aplicada assim: o aviso
pede para baixar de novo na página de download. Nesse caso, instale por cima (o instalador
substitui a versão antiga) ou, na versão portátil, apague a pasta antiga e extraia a nova.

## 7. O que o FleetDesk ainda não faz

Para usar com segurança, saiba destes limites da versão atual:

- **Ele só lê as planilhas.** Os lançamentos continuam sendo feitos no Excel.
- **O resultado operacional depende das abas COMBUSTÍVEL e PEDÁGIO.** Se elas estiverem vazias,
  o resultado e a margem aparecem maiores do que são de verdade (a Auditoria avisa).
- **A fatura do Sem Parar ainda não é importada.** Os pedágios precisam estar na aba PEDÁGIO.
- **Planilhas no modelo antigo** (uma aba por motorista) aparecem como *Ignoradas*.
- **As abas FECHAMENTO e RESULTADO POR PLACA não têm coluna de competência:** o FleetDesk usa a
  competência da maioria dos fretes da mesma planilha.
- **O instalador ainda não tem assinatura digital:** o Windows avisa antes de instalar, e em
  computadores com o Controle Inteligente de Aplicativos é preciso usar a versão portátil.

## 8. Privacidade

O FleetDesk roda só neste computador e **os dados das planilhas nunca saem dele**. As planilhas
são lidas no lugar onde estão, e as configurações ficam em `%APPDATA%\FleetDesk`.

A única conexão com a internet é a verificação de versões novas, que consulta a página de
versões do projeto no GitHub e não envia nenhum dado seu. Ela pode ser desligada em
**Configurações > Atualizações**.

## 9. Problemas comuns

| Problema | O que fazer |
|---|---|
| Aviso "O Windows protegeu o computador" ao instalar | Clique em **Mais informações > Executar assim mesmo** |
| O Windows bloqueia o instalador sem opção de executar | Use a versão portátil (item 2, *Se o Windows bloquear o instalador*) |
| Aparece "Extraia o arquivo .zip..." | Você abriu a versão portátil de dentro do `.zip`. Extraia antes |
| "Atualizar agora" mostra um erro | Confira a internet e tente de novo. Se continuar, baixe a versão nova na página de download |
| Uma planilha aparece como *Ignorada* | Ela não está no modelo FRETES (V2). Confira se tem a aba `LANÇAMENTOS` |
| Aparece *Erro ao ler* | A planilha pode estar sendo salva ou sincronizada. Espere um pouco e clique em **Recarregar** |
| Aviso de "fretes repetidos" | Há duas planilhas iguais na pasta (por exemplo, "Cópia de..."). Remova a cópia |
| Números não mudaram depois de salvar | Espere o Google Drive terminar de sincronizar e clique em **Recarregar** |
| "O Ollama não está aberto" na Auditoria | Abra o aplicativo Ollama (ou ignore: a IA é opcional) |
| Outro problema | Envie o arquivo `%APPDATA%\FleetDesk\fleetdesk.log` para o suporte |

## 10. Desinstalar

- **Instalado pelo instalador:** abra **Configurações do Windows > Aplicativos**, procure
  **FleetDesk** e clique em **Desinstalar**.
- **Versão portátil:** apague a pasta do FleetDesk e o ícone da Área de Trabalho.

As configurações ficam guardadas para uma eventual reinstalação. Para apagá-las também, apague a
pasta `%APPDATA%\FleetDesk`.
