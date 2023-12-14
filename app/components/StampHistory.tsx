import { StampSends } from "$components/StampSends.tsx";

export function StampHistory({ holders, sends }: { holders: HolderRow[], sends: SendRow[] }) {
  return (
    <div class="">
      <StampSends sends={sends} />
    </div>
  )

}