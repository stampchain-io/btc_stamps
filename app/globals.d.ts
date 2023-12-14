type SUBPROTOCOLS = "STAMP" | "SRC-20" | "SRC-721";

interface BlockRow {
  block_index: number;
  block_hash: string;
  block_time: number | Date;
  previous_block_hash: string;
  difficulty: number;
  ledger_hash: string;
  txlist_hash: string;
  messages_hash: string;
  indexed: 1;
  issuances?: number;
  sends?: number;
}
interface StampRow {
  stamp: number | null;
  block_index: number;
  cpid: string;
  asset_longname: string | null;
  creator: string;
  divisible: number;
  keyburn: number | null;
  locked: number;
  message_index: number;
  stamp_base64: string;
  stamp_mimetype: string;
  stamp_url: string;
  supply: number;
  timestamp: Date;
  tx_hash: string;
  tx_index: number;
  src_data: null;
  ident: SUBPROTOCOLS;
  creator_name: string | null;
  stamp_gen: null;
  stamp_hash: string;
  is_btc_stamp: number;
  is_reissue: number | null;
  file_hash: string;
}

interface SendRow {
  from: string;
  to: string;
  cpid: string|null;
  tick: string|null;
  memo: string;
  quantity: BigInt;
  tx_hash: string;
  tx_index: number;
  block_index: number;
}

interface BlockInfo {
  block_info: BlockRow;
  issuances: StampRow[];
  sends: SendRow[];
}

interface XCPParams {
  filters?: {
    field: string;
    op: string;
    value: string;
  }[];
  address?: string;
  asset?: string;
}