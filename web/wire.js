// The games' binary snapshot frames (engine/wire.py), read in the browser.
//
// A frame starts with one kind byte (1 = snapshot), then the header <IHBBH>: server_ms, seq, count, flags, ack,
// all little-endian; then count records, each an id byte followed by the schema's fields. Every number is a
// scaled integer on the wire (centimetres, yaw x 10...), divided back here.

export const KIND_SNAPSHOT = 1;

// kart_sim.SCHEMA_FIELDS: name, struct code, scale
export const KART_FIELDS = [["x", "i", 100], ["y", "i", 100], ["yaw", "h", 10], ["v", "h", 100], ["u", "h", 100],
                            ["charge", "H", 1], ["boost", "B", 1], ["slip", "B", 1], ["lap", "B", 1],
                            ["cp", "B", 1], ["flags", "B", 1], ["steer", "b", 100],
                            ["dw", "H", 1], ["dfl", "H", 1], ["dfr", "H", 1], ["drl", "H", 1], ["drr", "H", 1],
                            ["de", "H", 1],  // (each part's damage: CHANGE 158)
                            ["item", "B", 1], ["shield", "H", 1],  // (the item held; shield ticks left: CHANGE 159)
                            ["bg", "B", 1],  // (a bump's grace: CHANGE 159)
                            ["tyre", "H", 10000]];  // (tyre wear, 0 to 1: CHANGE 178)

const READ = {
    b: (dv, o) => [dv.getInt8(o), 1], B: (dv, o) => [dv.getUint8(o), 1],
    h: (dv, o) => [dv.getInt16(o, true), 2], H: (dv, o) => [dv.getUint16(o, true), 2],
    i: (dv, o) => [dv.getInt32(o, true), 4], I: (dv, o) => [dv.getUint32(o, true), 4],
};

export function kindOf(buf) {
    return buf.byteLength ? new DataView(buf).getUint8(0) : 0;
}

export function unpackSnapshot(buf, fields = KART_FIELDS) {
    const dv = new DataView(buf);
    if (dv.getUint8(0) !== KIND_SNAPSHOT) throw new Error("not a snapshot frame");
    const sm = dv.getUint32(1, true), seq = dv.getUint16(5, true), count = dv.getUint8(7);
    const flags = dv.getUint8(8), ack = dv.getUint16(9, true);
    let off = 11;
    const entities = [];
    for (let c = 0; c < count; c++) {
        const e = {id: dv.getUint8(off++)};
        for (const [name, code, scale] of fields) {
            const [v, size] = READ[code](dv, off);
            off += size;
            e[name] = scale === 1 ? v : v / scale;
        }
        entities.push(e);
    }
    return {sm, seq, ack, flags, entities};
}
