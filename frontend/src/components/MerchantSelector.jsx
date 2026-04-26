export default function MerchantSelector({ merchants, selected, onSelect }) {
  return (
    <select
      id="merchant-selector"
      value={selected || ''}
      onChange={(e) => onSelect(e.target.value)}
      className="input-field max-w-[220px] text-sm cursor-pointer appearance-none bg-no-repeat"
      style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%23748ffc' stroke-width='2'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E")`,
        backgroundPosition: 'right 12px center',
        backgroundSize: '16px',
        paddingRight: '36px',
      }}
    >
      {merchants.map((m) => (
        <option key={m.id} value={m.id} className="bg-surface-900 text-white">
          {m.name}
        </option>
      ))}
    </select>
  );
}
