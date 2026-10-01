function drawQrLike(container, text, size) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0,0,size,size);

  const n = 29;
  const cell = size / n;
  let h = 2166136261;
  for (let i=0;i<text.length;i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  function bit(x,y) {
    let v = (h ^ Math.imul(x+1, 73856093) ^ Math.imul(y+1, 19349663)) >>> 0;
    v ^= v << 13; v ^= v >>> 17; v ^= v << 5;
    return v & 1;
  }
  function finder(x,y) {
    ctx.fillStyle = "#111827";
    ctx.fillRect(x*cell,y*cell,7*cell,7*cell);
    ctx.fillStyle = "#fff";
    ctx.fillRect((x+1)*cell,(y+1)*cell,5*cell,5*cell);
    ctx.fillStyle = "#111827";
    ctx.fillRect((x+2)*cell,(y+2)*cell,3*cell,3*cell);
  }
  ctx.fillStyle = "#111827";
  for(let y=0;y<n;y++){
    for(let x=0;x<n;x++){
      const reserved = (x<8&&y<8)||(x>n-9&&y<8)||(x<8&&y>n-9);
      if(!reserved && bit(x,y)) ctx.fillRect(x*cell,y*cell,Math.ceil(cell),Math.ceil(cell));
    }
  }
  finder(1,1); finder(n-8,1); finder(1,n-8);
  container.innerHTML = "";
  container.appendChild(canvas);
}
