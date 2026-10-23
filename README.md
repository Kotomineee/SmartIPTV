# SmartIPTV

Aplicativo para Windows para reproduzir playlists IPTV pelo método **Xtream**, desenvolvido em Python com PySide6.

**v1.0.0:** login Xtream, sessão protegida pelo Windows, catálogo com categorias, reprodução, favoritos e continuar assistindo para filmes e episódios. Mantém o visual escuro com destaque em verde.

Baixe o aplicativo na página de [Releases](https://github.com/Kotomineee/SmartIPTV/releases).

Para executar pelo código, com Python 3.12 ou superior:

```sh
python -m pip install -r requirements.txt
python main.py
```

Marque **Manter conectado nesse computador** para entrar automaticamente nas próximas aberturas. Favoritos e progresso ficam salvos localmente, separados por conta. Use **Sair da conta** para remover a sessão salva.

Requer Windows 10/11 de 64 bits e uma conta Xtream ativa. O conteúdo, os metadados e a disponibilidade das transmissões dependem do provedor. Em Início, filmes usam a data de inclusão e séries usam a data da última atualização. TV ao vivo abre no sinal atual.
