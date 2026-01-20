const rawData = `data:As

data: a

data: financial

data: analyst`;

const lines = rawData.split('\n');
let result = '';

for (const line of lines) {
  if (line.startsWith('data:')) {
    // 关键点：这里应该截取第5个字符之后的所有内容
    const content = line.substring(5); 
    result += content;
  }
}

console.log("Parsed Result:", result);
