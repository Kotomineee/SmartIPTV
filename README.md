# SmartIPTV

Aplicativo para Windows para reproduzir playlists IPTV pelo método **Xtream**, desenvolvido em Python com PySide6.

**v1.1.0:** login Xtream, catálogo com categorias, favoritos e continuar assistindo. Player na mesma janela, seleção de áudio e legenda e reprodução automática do próximo episódio. Visual escuro com destaque em verde.

Baixe o aplicativo na página de [Releases](https://github.com/Kotomineee/SmartIPTV/releases).

Para executar pelo código, com Python 3.12 ou superior:

```sh
python -m pip install -r requirements.txt
python main.py
```

Marque **Manter conectado nesse computador** para entrar automaticamente nas próximas aberturas, com a sessão protegida pelo Windows. Favoritos e progresso ficam salvos localmente, separados por conta. Em **Configurações**, atualize os conteúdos, ative **Reproduzir próximo episódio** ou use **Sair da conta** para remover a sessão salva. A preferência de reprodução fica salva neste computador.

Requer Windows 10/11 de 64 bits e uma conta Xtream ativa. Conteúdos, vencimento e conexões dependem dos dados do provedor. Faixas de áudio e legendas aparecem quando disponíveis e compatíveis com o player. Em Início, filmes usam a data de inclusão e séries usam a última atualização. TV ao vivo abre no sinal atual.
