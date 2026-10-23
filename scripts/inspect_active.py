import pandas as pd

df = pd.read_csv('reports/secular_longterm_hold/secular_multibagger_campaigns_2015_2026.csv')
active = df[df['status'] == 'Active'].sort_values('net_return_pct', ascending=False)
print(f'Total active: {len(active)}')
for _, r in active.iterrows():
    print(f"{r['symbol']:12} | Entry: {r['entry_date']} @ {r['entry_price']:.1f} | Current: {r['exit_date']} @ {r['exit_price']:.1f} | Days: {r['days_held']:4d} ({r['days_held']/365:.1f}y) | Net Return: +{r['net_return_pct']:.1f}%")
