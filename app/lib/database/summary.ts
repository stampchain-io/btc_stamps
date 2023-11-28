import { get_issuances_by_identifier } from "./index.ts"

export const summarize_issuances = async (issuances: StampRow[]) => {
    const summary = {
        ...issuances[0],
    };
    issuances.splice(1).forEach((issuance) => {
        summary.supply += issuance.supply;
        if (issuance.locked === 1) {
            summary.locked = 1;
        }
    });
    return summary;
}