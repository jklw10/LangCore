@import(tests/std.w);
@using(sys);

ptr, length = @embed(tests/hw.txt);
sys.write(ptr, length);