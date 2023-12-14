export function StampKind({ kind }: { kind: 'stamp' | 'cursed' | 'named' }) {
  const getTooltipText = (kind) => {
    const tooltipTexts = {
      stamp: 'Bitcoin Stamp',
      cursed: 'Cursed Stamp',
      named: 'Named Stamp'
    };
    return tooltipTexts[kind] || '';
  };

  return (
    <div className="flex items-center">
      {kind === 'stamp' && (
        <div className="flex flex-row gap-2">
          <img src="/img/btc_stamp_white.svg" width="42px" alt="Stamp" />
        </div>
      )}
      {kind === 'cursed' && (
        <div className="flex flex-row gap-2">
          <img src="/img/cursed_white.svg" width="42px" alt="Cursed" />
        </div>
      )}
      {kind === 'named' && (
        <div className="flex flex-row gap-2">
            <img src="/img/cursed_white.svg" width="42px" alt="Cursed" />
            <img src="/img/named_white.svg" width="42px" alt="Named" />
        </div>
      )}
    </div>
  );
}
