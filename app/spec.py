COLUMNS = ('parcel', 'entry', 'exit', 'observed', 'basis_points')
KINDS = ('arrival', 'pickup', 'observation')
PROJECT = {'name': '柜件滞留估计台', 'actor': '自提柜运营分析员', 'stages': [('intake', '样例采信'), ('prepare', '观察队列'), ('calculate', '生存率计算'), ('policy', '滞留复核'), ('balance', '运行对账')], 'chart': '滞留曲线', 'mark': '柜'}
