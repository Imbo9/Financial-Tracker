import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { accountQueries } from '../../api/queries';
import type { AccountBalance, AccountType } from '../../api/types';
import styles from './AccountModal.module.css';

const TYPES: AccountType[] = ['cash', 'bank', 'card', 'savings'];

interface Props {
  account: AccountBalance | null; // null = create
  onClose: () => void;
  onSaved: () => void;
}

export function AccountModal({ account, onClose, onSaved }: Props) {
  const isEdit = account !== null;
  const isManual = account?.is_manual ?? true;
  const [name, setName] = useState(account?.display_name ?? '');
  const [type, setType] = useState<AccountType>(account?.type ?? 'cash');
  const [opening, setOpening] = useState(String(account?.opening_balance ?? ''));

  const create = useMutation({ ...accountQueries.create(), onSuccess: onSaved });
  const update = useMutation({ ...accountQueries.update(), onSuccess: onSaved });
  const pending = create.isPending || update.isPending;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isEdit) {
      update.mutate({
        account_id: account.account_id,
        display_name: name,
        type,
        ...(isManual ? { opening_balance: Number(opening) || 0 } : {}),
      });
    } else {
      create.mutate({ display_name: name, type, opening_balance: Number(opening) || 0 });
    }
  };

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <form className={styles.form} onSubmit={submit}>
          <label className={styles.field}>
            <span className={styles.label}>Name</span>
            <input className={styles.input} value={name} onChange={e => setName(e.target.value)} />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Type</span>
            <select
              className={styles.input}
              value={type}
              onChange={e => setType(e.target.value as AccountType)}
            >
              {TYPES.map(t => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          {isManual && (
            <label className={styles.field}>
              <span className={styles.label}>Opening balance</span>
              <input
                className={styles.input}
                type="number"
                step="0.01"
                value={opening}
                onChange={e => setOpening(e.target.value)}
              />
            </label>
          )}
          {(create.isError || update.isError) && (
            <div className={styles.error}>Impossibile salvare — riprova.</div>
          )}
          <button type="submit" disabled={pending || !name} className={styles.save}>
            {pending ? 'Saving…' : 'Save'}
          </button>
        </form>
      </div>
    </div>
  );
}
