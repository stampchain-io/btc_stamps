import { load } from "$std/dotenv/mod.ts";
import { Client } from "$mysql/mod.ts";

// Load .env file
const env_file = Deno.env.get("ENV") === "development" ? "./.env.development.local" : "./.env";

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
  client.close();
  return result;
};

export const handleQueryWithClient = async (client: Client, query: string, params: String[]) => {
  const result = await client.execute(query, params);
  return result;
};