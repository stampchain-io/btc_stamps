import { Client } from "$mysql/mod.ts";
import {
  handleQuery,
  handleQueryWithClient,
  get_issuances_by_identifier_with_client,
  get_issuances_by_stamp_with_client,
  summarize_issuances,
} from './index.ts';
import { STAMP_TABLE } from "constants"

export const get_total_stamps = async () => {
  return await handleQuery(
    `
    SELECT COUNT(*) AS total
    FROM ${STAMP_TABLE}
    WHERE is_btc_stamp IS NOT NULL;
    `,
    []
  );
};

export const get_total_stamps_with_client = async (client: Client) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT COUNT(*) AS total
    FROM ${STAMP_TABLE}
    WHERE is_btc_stamp IS NOT NULL;
    `,
    []
  );
};

export const get_total_stamps_by_ident = async (ident: SUBPROTOCOLS) => {
  return await handleQuery(
    `
    SELECT COUNT(*) AS total
    FROM ${STAMP_TABLE}
    WHERE ident = ?
    AND is_btc_stamp IS NOT NULL;
    `,
    [ident]
  );
};

export const get_total_stamps_by_ident_with_client = async (client: Client, ident: SUBPROTOCOLS) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT COUNT(*) AS total
    FROM ${STAMP_TABLE}
    WHERE ident = ?
    AND is_btc_stamp IS NOT NULL;
    `,
    [ident]
  );
};

export const get_stamps_by_page = async (limit = 1000, page = 0) => {
  const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
  return await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE is_btc_stamp IS NOT NULL
    ORDER BY stamp
    LIMIT ? OFFSET ?;
    `,
    [limit, offset]
  );
};

export const get_stamps_by_page_with_client = async (client: Client, limit = 1000, page = 0) => {
  const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
  return await handleQueryWithClient(
    client,
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE is_btc_stamp IS NOT NULL
    ORDER BY stamp
    LIMIT ? OFFSET ?;
    `,
    [limit, offset]
  );
};

export const get_resumed_stamps_by_page_with_client = async (client: Client, limit = 1000, page = 1, order = "DESC") => {
  order = order.toUpperCase() === 'ASC' ? 'ASC' : 'DESC';
  const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
  return await handleQueryWithClient(
    client,
    `
    SELECT stamp, cpid, creator, creator_name, tx_hash, stamp_mimetype, supply, divisible, locked
    FROM ${STAMP_TABLE}
    WHERE is_btc_stamp IS NOT NULL
    ORDER BY tx_index ${order}
    LIMIT ? OFFSET ?;
    `,
    [limit, offset]
  );
};

export const get_stamps_by_block_index = async (block_index: number) => {
  return await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE block_index = ?
    AND is_btc_stamp IS NOT NULL
    ORDER BY stamp
    `,
    [block_index]
  );
};

export const get_stamps_by_block_index_with_client = async (client: Client, block_index: number) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE block_index = ?
    AND is_btc_stamp IS NOT NULL
    ORDER BY stamp
    `,
    [block_index]
  );
};

export const get_stamps_by_ident = async (ident: SUBPROTOCOLS, limit = 1000, page = 0) => {
  const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
  return await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE ident = ?
    AND is_btc_stamp IS NOT NULL
    ORDER BY stamp
    LIMIT ? OFFSET ?;
    `,
    [ident, limit, offset]
  );
};

export const get_stamps_by_ident_with_client = async (client: Client, ident: SUBPROTOCOLS, limit = 1000, page = 0) => {
  const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
  return await handleQueryWithClient(
    client,
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE ident = ?
    AND is_btc_stamp IS NOT NULL
    ORDER BY stamp
    LIMIT ? OFFSET ?;
    `,
    [ident, limit, offset]
  );
};

export const get_stamp_by_stamp = async (stamp: number) => {
  return await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE stamp = ?
    ORDER BY tx_index;
    `,
    [stamp]
  );
};

export const get_stamp_by_stamp_with_client = async (client: Client, stamp: number) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE stamp = ?;
    `,
    [stamp]
  );
};

export const get_stamp_by_identifier = async (identifier: string) => {
  return await handleQuery(
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE (cpid = ? OR tx_hash = ? OR stamp_hash = ?);
    `,
    [identifier, identifier, identifier]
  );
};

export const get_stamp_by_identifier_with_client = async (client: Client, identifier: string) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT * FROM ${STAMP_TABLE}
    WHERE (cpid = ? OR tx_hash = ? OR stamp_hash = ?);
    `,
    [identifier, identifier, identifier]
  );
};

export const get_stamp = async (id: string) => {
  if (!isNaN(Number(id))) {
    return await get_stamp_by_stamp(Number(id));
  } else {
    return await get_stamp_by_identifier(id);
  }
}

export const get_stamp_with_client = async (client: Client, id: string) => {
  let data;
  if (!isNaN(Number(id))) {
    data = await get_issuances_by_stamp_with_client(client, Number(id));
  } else {
    data = await get_issuances_by_identifier_with_client(client, id);
  }
  const stamp =  summarize_issuances(data.rows);
  return stamp;
}

export const get_cpid_from_identifier = async (identifier: string) => {
  return await handleQuery(
    `
    SELECT cpid FROM ${STAMP_TABLE}
    WHERE (cpid = ? OR tx_hash = ? OR stamp = ?);
    `,
    [identifier, identifier, identifier]
  );
}

export const get_cpid_from_identifier_with_client = async (client: Client, identifier: string) => {
  return await handleQueryWithClient(
    client,
    `
    SELECT cpid FROM ${STAMP_TABLE}
    WHERE (cpid = ? OR tx_hash = ? OR stamp = ?);
    `,
    [identifier, identifier, identifier]
  );
}