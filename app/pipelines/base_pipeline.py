from abc import ABC, abstractmethod


class BasePipeline(ABC):

    def run(self):

        df = self.extract()

        df = self.clean(df)

        df = self.validate(df)

        df = self.transform(df)

        self.load(df)

        return df

    @abstractmethod
    def extract(self):
        pass

    def clean(self, df):
        return df

    def validate(self, df):
        return df

    @abstractmethod
    def transform(self, df):
        pass

    @abstractmethod
    def load(self, df):
        pass