"""SendFast Q1 2024 analysis: Python code.

Copied from notebooks/SendFast_Analysis.ipynb (one "# %%" block per notebook cell).
The notebook is the main version, with the write-up and outputs.
All data is synthetic; SendFast is a fictional company.
"""
from IPython.display import display

# %%
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

pd.set_option('display.width', 160)
plt.rcParams.update({'figure.figsize': (9, 4), 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.grid': True, 'grid.alpha': 0.3, 'font.size': 10})
# SendFast brand colours, sampled from the logo
BLUE, ORANGE, GREY = '#434c54', '#e66227', '#a3a9b3'   # BLUE = brand slate, kept as the variable name

DATA = '../data/'
df_transactions = pd.read_csv(DATA + 'transactions.csv')
df_users = pd.read_csv(DATA + 'users.csv')
print(df_transactions.shape, df_users.shape)

# %%
# Transactions: consistent snake_case names (spelling 'receive' correctly)
df_transactions = df_transactions.rename(columns={
    'Id': 'id', 'DateCreated': 'date', 'UserId': 'user_id', 'SendAmount': 'send_amount',
    'SendCurrencyId': 'send_currency', 'ReceiveAmount': 'receive_amount',
    'ReceiveCurrencyId': 'receive_currency', 'Narration': 'narration',
    'ExchangeRate': 'rate', 'BaseAmount': 'base_amount_cad'})
df_transactions['date'] = pd.to_datetime(df_transactions['date']).dt.strftime('%Y-%m-%d')
df_transactions['corridor'] = df_transactions['send_currency'] + '→' + df_transactions['receive_currency']
# Same-currency 'transfers' are account/wallet debits, not remittances (see Section 2)
df_transactions['is_remittance'] = df_transactions['send_currency'] != df_transactions['receive_currency']

# Users: this export is already snake_case apart from one column
df_users = df_users.rename(columns={'Is_deactivated': 'is_deactivated'})
df_users['country'] = df_users['country'].str.title()
df_users['region'] = df_users['region'].str.title().fillna('Unknown')
df_users['occupation'] = df_users['occupation'].fillna('Undisclosed')
# KYC code-to-label mapping (code 5 does not occur; source of mapping unconfirmed)
df_users['kyc_status'] = df_users['kyc_status'].replace(
    {1: 'NOT_STARTED', 2: 'PENDING', 3: 'PASSED', 4: 'IN_REVIEW', 6: 'FAILED'})
df_users['dob'] = pd.to_datetime(df_users['dob'].replace('#NAME?', pd.NA).str.split(' ').str[0], errors='coerce')

print('Duplicate transaction ids:', df_transactions['id'].duplicated().sum())
print('Duplicate user ids:', df_users['user_id'].duplicated().sum())
print('Transactions with no user_id:', df_transactions['user_id'].isna().sum())

# %%
txn_users = set(df_transactions['user_id'].dropna())
signup_users = set(df_users['user_id'])
matched = txn_users & signup_users
m_rows = df_transactions['user_id'].isin(signup_users)
print(f'People who transacted: {len(txn_users):,}')
print(f'...of whom appear in the users table: {len(matched):,} ({len(matched)/len(txn_users):.1%})')
print(f'Share of transfers / value from matched users: {m_rows.mean():.1%} / '
      f'{df_transactions.loc[m_rows, "base_amount_cad"].sum() / df_transactions["base_amount_cad"].sum():.1%}')

# Does the users table cover every sender, or only new signups?
first_txn = (df_transactions[m_rows].groupby('user_id')['date'].min().rename('first_txn')
             .reset_index().merge(df_users[['user_id', 'signup_date']], on='user_id'))
days = (pd.to_datetime(first_txn['first_txn']) - pd.to_datetime(first_txn['signup_date'])).dt.days
print(f'Matched users whose first transfer is before signup: {(days < 0).sum()}  (median days to first transfer: {days.median():.0f})')
unm = df_transactions[~m_rows & df_transactions['user_id'].notna() & (df_transactions['date'] >= '2024-01-01')]
always = (unm.groupby('user_id')['date'].apply(lambda d: d.str[:7].nunique()) == 3).sum()
print(f'Unmatched users active in all of Jan, Feb and Mar: {always:,}')

# %%
dq = {
    'December data is partial (only 31 Dec present)': df_transactions['date'].str[:7].eq('2023-12').sum(),
    'Transfers with base amount of 0': (df_transactions['base_amount_cad'] <= 0).sum(),
    'Same-currency debits (NGN→NGN, CAD→CAD)': (~df_transactions['is_remittance']).sum(),
    'Users with placeholder DOB 2001-01-01': (df_users['dob'] == '2001-01-01').sum(),
    'Users aged over 100 at 31 Mar 2024': ((pd.Timestamp('2024-03-31') - df_users['dob']).dt.days / 365.25 > 100).sum(),
    'kyc_verified=True but status not PASSED': (df_users['kyc_verified'] & (df_users['kyc_status'] != 'PASSED')).sum(),
}
display(pd.Series(dq, name='rows').to_frame())

print(df_transactions.loc[~df_transactions['is_remittance']].groupby('corridor')['narration']
      .agg(lambda s: s.value_counts(normalize=True).head(1).round(3).to_dict()))
print(pd.crosstab(df_users['dob'] == '2001-01-01', df_users['gender']))

# %%
conn = sqlite3.connect(':memory:')
df_users.assign(dob=df_users['dob'].dt.strftime('%Y-%m-%d')).to_sql('users', conn, index=False)
df_transactions.to_sql('transactions', conn, index=False)
conn.execute('CREATE INDEX ix_txn_user ON transactions(user_id)')
sql = lambda q: pd.read_sql_query(q, conn)

# %%
monthly = sql('''
SELECT STRFTIME('%Y-%m', date)            AS month,
       COUNT(DISTINCT user_id)            AS active_senders,
       COUNT(id)                          AS transfers,
       SUM(base_amount_cad)               AS value_cad,
       ROUND(AVG(base_amount_cad), 0)     AS avg_transfer_cad
FROM transactions
WHERE date >= '2024-01-01' AND user_id IS NOT NULL
GROUP BY 1 ORDER BY 1
''')
for c in ['active_senders', 'transfers', 'value_cad']:
    monthly[c + '_mom_%'] = (monthly[c].pct_change() * 100).round(1)
display(monthly)
jan, mar = monthly.iloc[0], monthly.iloc[-1]
print(f"Jan→Mar: senders {mar.active_senders/jan.active_senders-1:+.1%}, transfers {mar.transfers/jan.transfers-1:+.1%}, "
      f"value {mar.value_cad/jan.value_cad-1:+.1%}")

# %%
fig, ax = plt.subplots()
idx = monthly.set_index('month')[['active_senders', 'transfers', 'value_cad']]
(idx / idx.iloc[0] * 100).plot(ax=ax, marker='o', color=[GREY, BLUE, ORANGE])
ax.set_title('Senders and transfers are flat; value is falling (Jan = 100)')
ax.set_ylabel('Index'); ax.set_xlabel(''); ax.legend(['Active senders', 'Transfers', 'Value (CA$)'])
plt.show()

# %%
ret_m = sql('''
WITH act AS (SELECT DISTINCT user_id, STRFTIME('%Y-%m', date) m FROM transactions
             WHERE user_id IS NOT NULL AND date >= '2024-01-01')
SELECT a.m AS from_month, COUNT(a.user_id) AS senders,
       COUNT(b.user_id) AS retained,
       ROUND(COUNT(b.user_id) * 100.0 / COUNT(a.user_id), 1) AS retention_pct
FROM act a
LEFT JOIN act b ON a.user_id = b.user_id AND b.m = STRFTIME('%Y-%m', DATE(a.m || '-01', '+1 month'))
WHERE a.m < '2024-03'
GROUP BY 1
''')
display(ret_m)

# Weeks start Monday; only full weeks 1 Jan – 31 Mar
ret_w = sql('''
WITH act AS (SELECT DISTINCT user_id, DATE(date, 'weekday 0', '-6 days') w FROM transactions
             WHERE user_id IS NOT NULL AND date >= '2024-01-01')
SELECT a.w AS week, COUNT(a.user_id) AS senders, COUNT(b.user_id) AS retained,
       ROUND(COUNT(b.user_id) * 100.0 / COUNT(a.user_id), 1) AS retention_pct
FROM act a LEFT JOIN act b ON a.user_id = b.user_id AND b.w = DATE(a.w, '+7 days')
WHERE a.w < (SELECT MAX(w) FROM act)
GROUP BY 1 ORDER BY 1
''')
print(f"Average week-to-week retention: {ret_w['retention_pct'].mean():.1f}%")

# %%
fig, ax = plt.subplots()
ax.plot(pd.to_datetime(ret_w['week']), ret_w['retention_pct'], marker='o', color=GREY, label='Week to week')
ax.axhline(ret_m['retention_pct'].mean(), color=BLUE, lw=2, label=f"Month to month ({ret_m['retention_pct'].mean():.0f}%)")
ax.set_ylim(0, 100); ax.yaxis.set_major_formatter(mtick.PercentFormatter())
ax.set_title('Most senders come back monthly; fewer send every week'); ax.legend(); plt.show()

# %%
ticket = sql('''
SELECT STRFTIME('%Y-%m', date) AS month, corridor,
       ROUND(AVG(base_amount_cad), 0) AS avg_transfer_cad,
       COUNT(DISTINCT user_id)        AS senders,
       COUNT(id)                      AS transfers,
       ROUND(AVG(CASE WHEN corridor = 'CAD→NGN' THEN rate END), 0) AS avg_ngn_per_cad
FROM transactions
WHERE date >= '2024-01-01' AND corridor IN ('CAD→NGN', 'NGN→CAD')
GROUP BY 1, 2 ORDER BY 2, 1
''')
display(ticket)

# %%
cad = ticket[ticket['corridor'] == 'CAD→NGN'].set_index('month')
fig, ax = plt.subplots()
ax.bar(cad.index, cad['avg_transfer_cad'], color=BLUE, width=0.5)
ax.set_ylabel('Avg CAD→NGN transfer (CA$)', color=BLUE); ax.set_ylim(0, 260)
for x, y in zip(cad.index, cad['avg_transfer_cad']):
    ax.text(x, y + 4, f'${y:.0f}', ha='center')
ax2 = ax.twinx(); ax2.plot(cad.index, cad['avg_ngn_per_cad'], color=ORANGE, marker='o'); ax2.grid(False)
ax2.set_ylabel('NGN per CAD', color=ORANGE); ax2.set_ylim(800, 1200)
ax.set_title('As the naira weakened, Canadian senders sent fewer dollars per transfer')
plt.show()

# %%
corr = sql('''
SELECT corridor,
       COUNT(id)                                   AS transfers,
       COUNT(DISTINCT user_id)                     AS senders,
       SUM(base_amount_cad)                        AS value_cad,
       ROUND(AVG(base_amount_cad), 0)              AS avg_transfer_cad
FROM transactions WHERE is_remittance = 1
GROUP BY 1 ORDER BY value_cad DESC
''')
corr['transfer_share_%'] = (corr['transfers'] / corr['transfers'].sum() * 100).round(1)
corr['value_share_%'] = (corr['value_cad'] / corr['value_cad'].sum() * 100).round(1)
display(corr)

purpose = sql('''
SELECT corridor, narration, COUNT(*) AS n FROM transactions
WHERE corridor IN ('CAD→NGN', 'NGN→CAD') GROUP BY 1, 2
''')
purpose['share_%'] = (purpose['n'] / purpose.groupby('corridor')['n'].transform('sum') * 100).round(1)
display(purpose.sort_values(['corridor', 'n'], ascending=[True, False]).groupby('corridor').head(4))

# %%
top = corr.head(2).set_index('corridor')[['transfer_share_%', 'value_share_%']]
ax = top.plot.barh(color=[GREY, BLUE], figsize=(9, 3))
ax.xaxis.set_major_formatter(mtick.PercentFormatter()); ax.set_ylabel('')
ax.set_title('NGN→CAD: 13.5% of remittances, 48% of value'); ax.legend(['Share of transfers', 'Share of value'])
ax.invert_yaxis(); plt.show()

# %%
# How concentrated is value across customers?
uv = sql('SELECT user_id, SUM(base_amount_cad) v FROM transactions WHERE user_id IS NOT NULL GROUP BY 1 ORDER BY v DESC')
n = len(uv)
print(f'Top 1% of customers ({n//100:,}) = {uv.v.head(n//100).sum()/uv.v.sum():.0%} of value; '
      f'top 10% ({n//10:,}) = {uv.v.head(n//10).sum()/uv.v.sum():.0%}')

# %%
funnel = sql('''
WITH s AS (
  SELECT u.*, (SELECT 1 FROM transactions t WHERE t.user_id = u.user_id LIMIT 1) IS NOT NULL AS transacted
  FROM users u WHERE signup_date < '2024-03-01')
SELECT 1 stage, 'Signed up' AS step, COUNT(*) users FROM s
UNION ALL SELECT 2, 'Completed profile', SUM(completed_profile) FROM s
UNION ALL SELECT 3, 'Started KYC', SUM(kyc_status <> 'NOT_STARTED') FROM s
UNION ALL SELECT 4, 'KYC passed', SUM(kyc_status = 'PASSED') FROM s
UNION ALL SELECT 5, 'Transacted', SUM(transacted) FROM s
ORDER BY stage
''')
funnel['% of signups'] = (funnel['users'] / funnel['users'].iloc[0] * 100).round(1)
funnel['% of previous step'] = (funnel['users'] / funnel['users'].shift() * 100).round(1)
display(funnel)

# %%
fig, ax = plt.subplots(figsize=(9, 3.5))
ax.barh(funnel['step'], funnel['users'], color=[GREY, GREY, ORANGE, GREY, BLUE])
for y, (v, p) in enumerate(zip(funnel['users'], funnel['% of signups'])):
    ax.text(v + 150, y, f'{v:,}  ({p:.0f}%)', va='center')
ax.invert_yaxis(); ax.set_xlim(0, funnel['users'].max() * 1.25)
ax.set_title('Most signups never start KYC (Dec–Feb signups)'); plt.show()

# %%
# Signup-to-first-transfer rate and KYC progress by country (Dec–Feb cohort)
by_country = sql('''
WITH s AS (
  SELECT u.*, EXISTS (SELECT 1 FROM transactions t WHERE t.user_id = u.user_id) AS transacted
  FROM users u WHERE signup_date < '2024-03-01' AND country IN ('Canada', 'Nigeria'))
SELECT country, COUNT(*) AS signups,
       ROUND(AVG(kyc_status = 'NOT_STARTED') * 100, 1) AS never_started_kyc_pct,
       ROUND(AVG(kyc_status = 'PASSED') * 100, 1)      AS kyc_passed_pct,
       ROUND(AVG(transacted) * 100, 1)                 AS conversion_pct
FROM s GROUP BY 1
''')
display(by_country)

# %%
ref = sql('''
WITH s AS (
  SELECT u.*, EXISTS (SELECT 1 FROM transactions t WHERE t.user_id = u.user_id) AS transacted
  FROM users u WHERE signup_date < '2024-03-01' AND country IN ('Canada', 'Nigeria'))
SELECT country,
       CASE WHEN referred_by IS NOT NULL THEN 'Referred' ELSE 'Not referred' END AS grp,
       COUNT(*)                                        AS signups,
       ROUND(AVG(kyc_status <> 'NOT_STARTED') * 100, 1) AS started_kyc_pct,
       ROUND(AVG(kyc_status = 'PASSED') * 100, 1)       AS kyc_passed_pct,
       ROUND(AVG(transacted) * 100, 1)                 AS conversion_pct
FROM s GROUP BY 1, 2 ORDER BY 1, 2
''')
display(ref)
p = ref.pivot(index='country', columns='grp', values='conversion_pct')
print((p['Referred'] / p['Not referred']).round(1).rename('Conversion lift from referral (x)').to_string())

# %%
fig, ax = plt.subplots(figsize=(9, 3.5))
countries = ['Nigeria', 'Canada']; y = range(len(countries)); h = 0.38
for i, (grp, col) in enumerate([('Not referred', GREY), ('Referred', BLUE)]):
    bars = ax.barh([v + (i - 0.5) * h for v in y], p.loc[countries, grp], h, color=col, label=grp)
    ax.bar_label(bars, fmt='%.1f%%', padding=3)
ax.set_yticks(list(y), countries); ax.invert_yaxis(); ax.set_xlim(0, 32)
ax.xaxis.set_major_formatter(mtick.PercentFormatter()); ax.legend(loc='lower right')
ax.set_title('Signup → first transfer: referral helps most in Nigeria'); plt.show()

# %%
# Does referral also make new senders stay? Same window for everyone:
# repeat = another transfer within 30 days of the first (first transfer on or before 1 Mar);
# still sending = a transfer on days 31–60 (first transfer on or before 31 Jan).
tx = df_transactions.dropna(subset=['user_id']).assign(date=lambda d: pd.to_datetime(d['date']))
first = tx.groupby('user_id')['date'].min().rename('first_txn')
new = df_users[['user_id', 'referred_by']].merge(first, left_on='user_id', right_index=True)
new = new[new['first_txn'] <= '2024-03-01'].copy()
new['grp'] = new['referred_by'].notna().map({True: 'Referred', False: 'Not referred'})
days = tx.merge(new[['user_id', 'first_txn']], on='user_id')
days['day'] = (days['date'] - days['first_txn']).dt.days
new['repeat_30d'] = new['user_id'].isin(days.loc[days['day'].between(1, 30), 'user_id'])
new['active_31_60d'] = new['user_id'].isin(days.loc[days['day'].between(31, 60), 'user_id'])
eligible = new['first_txn'] <= '2024-01-31'
retention = pd.DataFrame({
    'new senders': new.groupby('grp').size(),
    'sent again within 30 days %': (new.groupby('grp')['repeat_30d'].mean() * 100).round(1),
    'still sending on days 31–60 %': (new[eligible].groupby('grp')['active_31_60d'].mean() * 100).round(1),
})
display(retention)

share = sql('''
SELECT STRFTIME('%Y-%m', signup_date) AS signup_month, COUNT(*) AS signups,
       ROUND(AVG(referred_by IS NOT NULL) * 100, 1) AS referred_share_pct
FROM users GROUP BY 1 ORDER BY 1
''')
display(share)
