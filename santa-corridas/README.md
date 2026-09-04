# Santa Corridas - Aplicativo de Corrida 🏃

Aplicação web completa para registro e acompanhamento de corridas, com estatísticas avançadas, metas, conquistas e ranking.

## ✨ Funcionalidades

### Autenticação
- Registro de usuários com validação
- Login/Logout
- Proteção de rotas (login_required)
- Alteração de senha
- Perfil de usuário com avatar, bio, peso e altura

### Corridas
- Registro de corridas (distância, duração, data, notas, percurso)
- Cálculo automático de ritmo (min/km)
- Cálculo automático de velocidade média (km/h)
- Cálculo de calorias queimadas (baseado no peso)
- Edição e exclusão de corridas
- Listagem com paginação
- Filtros por data e distância
- Exportação para CSV

### Dashboard
- Estatísticas agregadas (distância total, tempo, ritmo médio, etc.)
- Gráfico de barras: distância por mês
- Gráfico de linha: ritmo recente
- Metas ativas com progresso
- Conquistas recentes
- Últimas corridas registradas

### Metas
- Criar metas de distância mensal
- Criar metas de número de corridas
- Criar metas de ritmo alvo
- Visualizar progresso das metas
- Marcar metas como concluídas

### Conquistas (Badges)
- Medalhas automáticas por marcos:
  - Primeira corrida
  - Corridas de 5km, 10km, 21km
  - 50km e 100km acumulados
  - 10 corridas completadas

### Ranking
- Ranking global por distância total
- Comparação entre usuários

### Interface
- Design moderno com Bootstrap 5
- Ícones Bootstrap Icons
- Gráficos interativos com Chart.js
- Gradientes e animações CSS
- Totalmente responsivo (mobile-first)
- Mensagens de feedback (flash messages)

## 🚀 Instalação

### Pré-requisitos
- Python 3.8 ou superior
- pip (gerenciador de pacotes do Python)

### Passo a passo

1. **Clone ou extraia o projeto**
   ```bash
   git clone https://github.com/seu-usuario/santacorridas.git
   cd santacorridas
