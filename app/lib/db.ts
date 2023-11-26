import { load } from "$std/dotenv/mod.ts";
import { Client } from "$mysql/mod.ts";


export const connectDb = async () => {
    try {
        await load();
        const hostname = Deno.env.get("DB_HOST");
        const username = Deno.env.get("DB_USERNAME");
        const password = Deno.env.get("DB_PASSWORD");
        const port = Deno.env.get("DB_PORT");
        const db = Deno.env.get("DB_NAME");

        const client = await new Client().connect({
            hostname,
            port: Number(port),
            username,
            db,
            password,
        });
        return client;
    } catch (error) {
        console.error("ERROR: Error connecting db:",error);
    }
};

export const query = async (query: string, params: String[]) => {
    const client = await connectDb();
    const result = await client.useConnection(async (conn) => {
        const { iterator } = await conn.execute(
            query,
            params,
            true, // iterator
        );
        console.log(iterator);
        return iterator;
    });
    client.close();
    return result;
};