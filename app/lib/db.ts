import { load } from "$std/dotenv/mod.ts";
import { Client } from "$mysql/mod.ts";

// Load .env file
const env_file = Deno.env.get("ENV") === "development" ? "./.env.development.local": "./.env";

export const connectDb = async () => {
    try {
        const conf = await load({
            envPath: env_file,
            export: true,
        });
        const hostname = conf.DB_HOST;
        const username = conf.DB_USER;
        const password = conf.DB_PASSWORD;
        const port = conf.DB_PORT;
        const db = conf.DB_NAME;
        const client = await new Client().connect({
            hostname,
            port: Number(port),
            username,
            db,
            password,
        });
        return client;
    } catch (error) {
        console.error("ERROR: Error connecting db:", error);
    }
};

export const handleQuery = async (query: string, params: String[]) => {
    const client = await connectDb();
    const result = await client.execute(query, params);
    return result;
};

export const handleQueryWithClient = async (client: Client, query: string, params: String[]) => {
    const result = await client.execute(query, params);
    return result;
};

export const get_last_block = async () => {
    return await handleQuery(
        `
        SELECT MAX(block_index)
        AS last_block
        FROM blocks;
      `,
      []
    );
}

export const get_last_block_with_client = async (client: Client) => {
    return await handleQueryWithClient(
        client,
        `
        SELECT MAX(block_index)
        AS last_block
        FROM blocks;
      `,
      []
    );
}

export const get_total_stamps = async () => {
    return await handleQuery(
        `
        SELECT COUNT(*) AS total
        FROM StampTableV4
        WHERE is_btc_stamp IS NOT NULL;
        `,
      []
    );
}

export const get_total_stamps_with_client = async (client: Client) => {
    return await handleQueryWithClient(
        client,
        `
        SELECT COUNT(*) AS total
        FROM StampTableV4
        WHERE is_btc_stamp IS NOT NULL;
        `,
      []
    );
}

export const get_total_cursed = async () => {
    return await handleQuery(
        `
        SELECT COUNT(*) AS total
        FROM StampTableV4
        WHERE is_btc_stamp IS NULL
        AND is_reissue IS NULL;
        `,
      []
    );
}

export const get_total_cursed_with_client = async (client: Client) => {
    return await handleQueryWithClient(
        client,
        `
        SELECT COUNT(*) AS total
        FROM StampTableV4
        WHERE is_btc_stamp IS NULL
        AND is_reissue IS NULL;
        `,
      []
    );
}

export const get_stamps_by_page = async (limit=1000, page=0) => {
    const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
    return await handleQuery(
        `
          SELECT * FROM StampTableV4
          WHERE is_btc_stamp IS NOT NULL
          ORDER BY stamp
          LIMIT ? OFFSET ?;
          `,
        [limit, offset]
      );
};

export const get_stamps_by_page_with_client = async (client: Client, limit=1000, page=0) => {
    const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
    return await handleQueryWithClient(
        client,
        `
          SELECT * FROM StampTableV4
          WHERE is_btc_stamp IS NOT NULL
          ORDER BY stamp
          LIMIT ? OFFSET ?;
          `,
        [limit, offset]
      );
};

export const get_cursed_by_page = async (limit=1000, page=0) => {
    const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
    return await handleQuery(
        `
          SELECT * FROM StampTableV4
          WHERE is_btc_stamp IS NULL
          AND is_reissue IS NULL
          ORDER BY tx_index
          LIMIT ? OFFSET ?;
          `,
        [limit, offset]
      );
};

export const get_cursed_by_page_with_client = async (client: Client, limit=1000, page=0) => {
    const offset = limit && page ? Number(limit) * (Number(page) - 1) : 0;
    return await handleQueryWithClient(
        client,
        `
          SELECT * FROM StampTableV4
          WHERE is_btc_stamp IS NULL
          AND is_reissue IS NULL
          ORDER BY tx_index
          LIMIT ? OFFSET ?;
          `,
        [limit, offset]
      );
};

export const get_stamp_by_stamp = async (stamp: number) => {
    return await handleQuery(
        `
        SELECT * FROM StampTableV4
        WHERE stamp = ?;
        `,
        [stamp]
      );
};

export const get_stamp_by_stamp_with_client = async (client: Client, stamp: number) => {
    return await handleQueryWithClient(
        client,
        `
        SELECT * FROM StampTableV4
        WHERE stamp = ?;
        `,
        [stamp]
      );
};

export const get_stamp_by_identifier = async (identifier: string) => {
    return await handleQuery(
        `
        SELECT * FROM StampTableV4
        WHERE (cpid = ? OR tx_hash = ? OR stamp_hash = ?);
        `,
        [identifier, identifier, identifier]
      );
};

export const get_stamp_by_identifier_with_client = async (client: Client, identifier: string) => {
    return await handleQueryWithClient(
        client,
        `
        SELECT * FROM StampTableV4
        WHERE (cpid = ? OR tx_hash = ? OR stamp_hash = ?);
        `,
        [identifier, identifier, identifier]
      );
};