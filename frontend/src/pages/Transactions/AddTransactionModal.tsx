import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useQuery, useMutation } from '@tanstack/react-query';
import { transactionQueries, taxonomyQueries, accountQueries } from '../../api/queries';
import styles from './AddTransactionModal.module.css';

type TxType = 'income' | 'expense';

const schema = z.object({
  booking_date: z.string().min(1, 'Data obbligatoria'),
  amount: z.coerce.number().refine(v => v > 0, 'Importo maggiore di zero'),
  merchant_name: z.string().min(1, 'Nome obbligatorio'),
  category: z.string().optional(),
  subcategory: z.string().optional(),
  description: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

interface Props {
  onClose: () => void;
  onAdd: () => void;
}

export function AddTransactionModal({ onClose, onAdd }: Props) {
  const [type, setType] = useState<TxType>('expense');

  const form = useForm<z.input<typeof schema>, unknown, FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      booking_date: new Date().toISOString().slice(0, 10),
      merchant_name: '',
      category: '',
      subcategory: '',
      description: '',
    },
  });

  const { data: taxonomy } = useQuery({ ...taxonomyQueries.categories() });
  const sideCategories = (type === 'income' ? taxonomy?.income : taxonomy?.expense) ?? {};
  // useWatch instead of form.watch: the latter is flagged unmemoizable by the React Compiler
  const selectedCategory = useWatch({ control: form.control, name: 'category' });
  const subcategories = selectedCategory ? (sideCategories[selectedCategory] ?? []) : [];

  const { data: accountsData } = useQuery({ ...accountQueries.list() });
  const accountList = accountsData?.accounts ?? [];
  const [accountId, setAccountId] = useState<string>('');
  const effectiveAccountId = accountId || accountList[0]?.account_id || '';

  const mutation = useMutation({
    ...transactionQueries.create(),
    onSuccess: () => {
      onAdd();
      onClose();
    },
  });

  const onSubmit = form.handleSubmit(values => {
    const signed = type === 'income' ? Math.abs(values.amount) : -Math.abs(values.amount);
    mutation.mutate({
      booking_date: `${values.booking_date}T00:00:00Z`,
      amount: signed,
      eur_amount: signed,
      currency: 'EUR',
      merchant_name: values.merchant_name,
      account_id: effectiveAccountId || null,
      category: values.category || null,
      subcategory: values.subcategory || null,
      description: values.description || null,
    });
  });

  const { errors } = form.formState;

  return (
    <AnimatePresence>
      <motion.div
        className={styles.backdrop}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          className={styles.modal}
          initial={{ opacity: 0, y: 40, scale: 0.96 }}
          animate={{ opacity: 1, y: 0,  scale: 1 }}
          exit={{ opacity: 0, y: 40, scale: 0.96 }}
          transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
          onClick={e => e.stopPropagation()}
        >
          <div className={styles.header}>
            <div className={styles.typeTabs}>
              {(['income', 'expense'] as TxType[]).map(t => (
                <button
                  key={t}
                  type="button"
                  className={`${styles.typeTab} ${type === t ? styles.typeTabActive : ''} ${styles[t]}`}
                  onClick={() => {
                    setType(t);
                    form.setValue('category', '');
                    form.setValue('subcategory', '');
                  }}
                >
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
            <button type="button" className={styles.closeBtn} onClick={onClose}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
            </button>
          </div>

          <form className={styles.form} onSubmit={onSubmit}>
            <div className={styles.amountRow}>
              <span className={styles.currencyLabel}>€</span>
              <input
                className={styles.amountInput}
                type="number"
                step="0.01"
                min="0"
                placeholder="0.00"
                autoFocus
                {...form.register('amount')}
              />
            </div>
            {errors.amount && <span className={styles.fieldError}>{errors.amount.message}</span>}

            <div className={styles.fields}>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Merchant / Payee</span>
                <input className={styles.input} placeholder="e.g. Costa Coffee" {...form.register('merchant_name')} />
                {errors.merchant_name && <span className={styles.fieldError}>{errors.merchant_name.message}</span>}
              </label>

              <label className={styles.field}>
                <span className={styles.fieldLabel}>Date</span>
                <input className={styles.input} type="date" {...form.register('booking_date')} />
                {errors.booking_date && <span className={styles.fieldError}>{errors.booking_date.message}</span>}
              </label>

              {accountList.length > 0 && (
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>Account</span>
                  <select
                    className={styles.input}
                    value={effectiveAccountId}
                    onChange={e => setAccountId(e.target.value)}
                  >
                    {accountList.map(a => (
                      <option key={a.account_id} value={a.account_id}>
                        {a.display_name ?? a.account_id}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              <label className={styles.field}>
                <span className={styles.fieldLabel}>Category</span>
                <select
                  className={styles.input}
                  {...form.register('category', {
                    onChange: () => form.setValue('subcategory', ''),
                  })}
                >
                  <option value="">Select category</option>
                  {Object.keys(sideCategories).map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </label>

              {subcategories.length > 0 && (
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>Subcategory</span>
                  <select className={styles.input} {...form.register('subcategory')}>
                    <option value="">Select subcategory</option>
                    {subcategories.map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </label>
              )}

              <label className={styles.field}>
                <span className={styles.fieldLabel}>Note</span>
                <input className={styles.input} placeholder="Optional note" {...form.register('description')} />
              </label>
            </div>

            {mutation.isError && <div className={styles.formError}>Impossibile salvare — riprova.</div>}

            <button
              type="submit"
              disabled={mutation.isPending}
              className={`${styles.submitBtn} ${type === 'income' ? styles.submitIncome : styles.submitExpense}`}
            >
              {mutation.isPending ? 'Saving…' : `Add ${type.charAt(0).toUpperCase() + type.slice(1)}`}
            </button>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
