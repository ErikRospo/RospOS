



def main():
    temp:int=0
    a:int=1
    b:int=1
    for i in range(2,10):
        temp=a+b
        a=b
        b=temp
        print(temp)
    return 0