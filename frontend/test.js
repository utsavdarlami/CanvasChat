const nodes = [
  { id: '1', x: 147.4, y: 357.5, width: 740, height: 340, moved: false },
  { id: '2', x: 315.8, y: 357.5, width: 440, height: 340, moved: false }
];

let moved = false;
let iterations = 0;
do {
  moved = false;
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const A = nodes[i];
      const B = nodes[j];
      
      const centerAX = A.x + A.width * 0.5;
      const centerAY = A.y + A.height * 0.5;
      const centerBX = B.x + B.width * 0.5;
      const centerBY = B.y + B.height * 0.5;
      
      const dx = centerAX - centerBX;
      const dy = centerAY - centerBY;
      
      const px = (A.width + B.width) * 0.5 - Math.abs(dx);
      const py = (A.height + B.height) * 0.5 - Math.abs(dy);
      
      if (px > 0.5 && py > 0.5) {
        A.moved = B.moved = moved = true;
        const forceX = Math.abs(dy) < 1;
        const forceY = Math.abs(dx) < 1;
        if (forceX || (!forceY && px < py)) {
          const sx = dx > 0 ? 1 : -1;
          const moveAmount = (px / 2) * sx;
          A.x += moveAmount;
          B.x -= moveAmount;
        } else {
          const sy = dy > 0 ? 1 : -1;
          const moveAmount = (py / 2) * sy;
          A.y += moveAmount;
          B.y -= moveAmount;
        }
      }
    }
  }
  iterations++;
} while (moved && iterations < 50);

console.log(nodes);
